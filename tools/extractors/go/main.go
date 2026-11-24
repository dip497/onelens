// Go -> OneLens graph JSON, using the Go compiler's own type checker.
//
// Every Go module under <src_root> is loaded with golang.org/x/tools/go/packages
// and type-checked with go/types, so each call resolves to the exact function
// or method the compiler would bind. The output is the same JSON the IntelliJ
// plugin writes for Java, and `onelens import-graph` reads it unchanged.
//
// Go -> graph:
//
//	package            -> Class {kind: PACKAGE}  (owner of its top-level funcs)
//	struct / interface -> Class {kind: STRUCT | INTERFACE}; other named types -> TYPE
//	struct field       -> Field
//	func / method      -> Method (interface methods too, marked abstract)
//	call               -> CALLS, resolved by go/types (interface calls land on the
//	                      interface method; OVERRIDES fans them out to implementations)
//	embedded type      -> EXTENDS
//	T satisfies I      -> IMPLEMENTS, plus OVERRIDES from T's methods to I's
//
// Usage: go run . <src_root> [--name <graph>] [--goos linux,windows,darwin] > out.json
package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/token"
	"go/types"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"

	"golang.org/x/tools/go/packages"
)

const source = "TYPES"

type Class struct {
	Fqn            string `json:"fqn"`
	Name           string `json:"name"`
	Kind           string `json:"kind"`
	PackageName    string `json:"packageName"`
	SuperClass     string `json:"superClass"`
	EnclosingClass string `json:"enclosingClass"`
	FilePath       string `json:"filePath"`
	LineStart      int    `json:"lineStart"`
	LineEnd        int    `json:"lineEnd"`
	Source         string `json:"source"`
}

type Param struct {
	Name        string   `json:"name"`
	Type        string   `json:"type"`
	Annotations []string `json:"annotations"`
}

type Method struct {
	Fqn           string   `json:"fqn"`
	Name          string   `json:"name"`
	ClassFqn      string   `json:"classFqn"`
	ReturnType    string   `json:"returnType"`
	Parameters    []Param  `json:"parameters"`
	Modifiers     []string `json:"modifiers"`
	ThrowsTypes   []string `json:"throwsTypes"`
	Annotations   []any    `json:"annotations"`
	IsConstructor bool     `json:"isConstructor"`
	FilePath      string   `json:"filePath"`
	LineStart     int      `json:"lineStart"`
	LineEnd       int      `json:"lineEnd"`
	Body          string   `json:"body"`
	Javadoc       string   `json:"javadoc"`
	Source        string   `json:"source"`
}

type Field struct {
	Fqn       string `json:"fqn"`
	Name      string `json:"name"`
	ClassFqn  string `json:"classFqn"`
	Type      string `json:"type"`
	FilePath  string `json:"filePath"`
	LineStart int    `json:"lineStart"`
	Source    string `json:"source"`
}

type Call struct {
	CallerFqn string `json:"callerFqn"`
	CalleeFqn string `json:"calleeFqn"`
	Line      int    `json:"line"`
}

type Inheritance struct {
	ChildFqn     string `json:"childFqn"`
	ParentFqn    string `json:"parentFqn"`
	RelationType string `json:"relationType"`
}

type Override struct {
	MethodFqn    string `json:"methodFqn"`
	OverridesFqn string `json:"overridesFqn"`
}

type Doc struct {
	Version         string            `json:"version"`
	ExportType      string            `json:"exportType"`
	Project         map[string]string `json:"project"`
	Classes         []Class           `json:"classes"`
	Methods         []Method          `json:"methods"`
	Fields          []Field           `json:"fields"`
	CallGraph       []Call            `json:"callGraph"`
	Inheritance     []Inheritance     `json:"inheritance"`
	MethodOverrides []Override        `json:"methodOverrides"`
	Adapters        []string          `json:"adapters"`
}

type extractor struct {
	root       string
	doc        Doc
	seenClass  map[string]bool
	seenMethod map[string]bool
	named      []*types.Named // this load's named non-interface types
	interfaces []*types.Named // this load's named interfaces with at least one method
	seenEdge   map[string]bool
	loadErrors int
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: go run . <src_root> [--name <graph>] [--goos linux,windows,darwin]")
		os.Exit(2)
	}
	root, err := filepath.Abs(os.Args[1])
	if err != nil {
		fail(err)
	}
	name, goosList := filepath.Base(root), runtime.GOOS
	for i := 2; i < len(os.Args)-1; i++ {
		switch os.Args[i] {
		case "--name":
			name = os.Args[i+1]
		case "--goos":
			goosList = os.Args[i+1]
		}
	}
	e := &extractor{
		root: root,
		doc: Doc{
			Version: "1.0", ExportType: "full", Project: map[string]string{"name": name},
			Classes: []Class{}, Methods: []Method{}, Fields: []Field{}, CallGraph: []Call{},
			Inheritance: []Inheritance{}, MethodOverrides: []Override{}, Adapters: []string{"go-types"},
		},
		seenClass: map[string]bool{}, seenMethod: map[string]bool{}, seenEdge: map[string]bool{},
	}
	modules := findModules(root)
	if len(modules) == 0 {
		fail(fmt.Errorf("no go.mod under %s", root))
	}
	// Each platform reads a different set of *_windows.go / *_linux.go files;
	// loading every listed one and de-duplicating gives the union.
	for _, goos := range strings.Split(goosList, ",") {
		for _, dir := range modules {
			e.loadModule(dir, strings.TrimSpace(goos))
		}
	}
	fmt.Fprintf(os.Stderr, "go-types: %d modules, %d classes, %d methods, %d fields, %d calls, %d inheritance, %d overrides, %d packages with type errors\n",
		len(modules), len(e.doc.Classes), len(e.doc.Methods), len(e.doc.Fields), len(e.doc.CallGraph),
		len(e.doc.Inheritance), len(e.doc.MethodOverrides), e.loadErrors)
	if err := json.NewEncoder(os.Stdout).Encode(e.doc); err != nil {
		fail(err)
	}
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, "go-types:", err)
	os.Exit(1)
}

// findModules returns every directory under root holding a go.mod, skipping
// vendor, testdata and hidden folders.
func findModules(root string) []string {
	var dirs []string
	filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			n := d.Name()
			if path != root && (n == "vendor" || n == "testdata" || n == "node_modules" || strings.HasPrefix(n, ".")) {
				return filepath.SkipDir
			}
			return nil
		}
		if n := d.Name(); n == "go.mod" {
			dirs = append(dirs, filepath.Dir(path))
		}
		return nil
	})
	sort.Strings(dirs)
	return dirs
}

func (e *extractor) loadModule(dir, goos string) {
	cfg := &packages.Config{
		Mode: packages.NeedName | packages.NeedFiles | packages.NeedSyntax |
			packages.NeedTypes | packages.NeedTypesInfo | packages.NeedModule,
		Dir: dir,
		Env: append(os.Environ(), "GOOS="+goos),
	}
	// Type objects from different loads never compare equal, so implementations
	// are matched within this load only.
	e.named, e.interfaces = nil, nil
	defer e.linkImplementations()
	pkgs, err := packages.Load(cfg, "./...")
	if err != nil {
		fmt.Fprintf(os.Stderr, "go-types: load %s: %v\n", dir, err)
		return
	}
	for _, p := range pkgs {
		if len(p.Errors) > 0 {
			e.loadErrors++
			fmt.Fprintf(os.Stderr, "go-types: [%s] %s: %v\n", goos, p.PkgPath, p.Errors[0])
		}
		if p.Types == nil || p.TypesInfo == nil {
			continue
		}
		// Only packages whose files live inside this module (nested modules load on their own).
		if p.Module == nil || filepath.Clean(p.Module.Dir) != filepath.Clean(dir) {
			continue
		}
		e.emitPackage(p)
	}
}

func (e *extractor) rel(pos token.Position) string {
	r, err := filepath.Rel(e.root, pos.Filename)
	if err != nil {
		return pos.Filename
	}
	return filepath.ToSlash(r)
}

func (e *extractor) addClass(c Class) {
	if e.seenClass[c.Fqn] {
		return
	}
	e.seenClass[c.Fqn] = true
	e.doc.Classes = append(e.doc.Classes, c)
}

func (e *extractor) addEdge(key string) bool {
	if e.seenEdge[key] {
		return false
	}
	e.seenEdge[key] = true
	return true
}

func (e *extractor) addInheritance(child, parent, relation string) {
	if e.addEdge("I|" + child + "|" + parent + "|" + relation) {
		e.doc.Inheritance = append(e.doc.Inheritance, Inheritance{child, parent, relation})
	}
}

func (e *extractor) addMethod(m Method) {
	if e.seenMethod[m.Fqn] {
		return
	}
	e.seenMethod[m.Fqn] = true
	e.doc.Methods = append(e.doc.Methods, m)
}

func (e *extractor) emitPackage(p *packages.Package) {
	if len(p.Syntax) == 0 {
		return
	}
	first := p.Fset.Position(p.Syntax[0].Package)
	e.addClass(Class{
		Fqn: p.PkgPath, Name: p.Name, Kind: "PACKAGE", PackageName: p.PkgPath,
		FilePath: filepath.ToSlash(filepath.Dir(e.rel(first))), LineStart: 1, LineEnd: 1, Source: source,
	})
	for _, f := range p.Syntax {
		src, _ := os.ReadFile(p.Fset.Position(f.Pos()).Filename)
		for _, decl := range f.Decls {
			switch d := decl.(type) {
			case *ast.GenDecl:
				for _, spec := range d.Specs {
					if ts, ok := spec.(*ast.TypeSpec); ok {
						e.emitType(p, ts)
					}
				}
			case *ast.FuncDecl:
				e.emitFunc(p, d, src)
			}
		}
	}
}

func (e *extractor) emitType(p *packages.Package, ts *ast.TypeSpec) {
	obj, ok := p.TypesInfo.Defs[ts.Name].(*types.TypeName)
	if !ok || obj.IsAlias() {
		return
	}
	named, ok := obj.Type().(*types.Named)
	if !ok {
		return
	}
	fqn := typeFqn(named)
	start, end := p.Fset.Position(ts.Pos()), p.Fset.Position(ts.End())
	kind := "TYPE"
	switch u := named.Underlying().(type) {
	case *types.Struct:
		kind = "STRUCT"
		for i := 0; i < u.NumFields(); i++ {
			f := u.Field(i)
			fpos := p.Fset.Position(f.Pos())
			if f.Embedded() {
				if parent := namedOf(f.Type()); parent != nil {
					e.addInheritance(fqn, typeFqn(parent), "EXTENDS")
				}
				continue
			}
			if !e.addEdge("F|" + fqn + "#" + f.Name()) {
				continue
			}
			e.doc.Fields = append(e.doc.Fields, Field{
				Fqn: fqn + "#" + f.Name(), Name: f.Name(), ClassFqn: fqn, Type: typeStr(f.Type()),
				FilePath: e.rel(fpos), LineStart: fpos.Line, Source: source,
			})
		}
		e.named = append(e.named, named)
	case *types.Interface:
		kind = "INTERFACE"
		for i := 0; i < u.NumEmbeddeds(); i++ {
			if parent := namedOf(u.EmbeddedType(i)); parent != nil {
				e.addInheritance(fqn, typeFqn(parent), "EXTENDS")
			}
		}
		for i := 0; i < u.NumExplicitMethods(); i++ {
			m := u.ExplicitMethod(i)
			mpos := p.Fset.Position(m.Pos())
			e.addMethod(e.method(m, fqn, mpos, mpos, []string{visibility(m.Name()), "abstract"}, "", ""))
		}
		if u.NumMethods() > 0 {
			e.interfaces = append(e.interfaces, named)
		}
	default:
		e.named = append(e.named, named)
	}
	e.addClass(Class{
		Fqn: fqn, Name: obj.Name(), Kind: kind, PackageName: obj.Pkg().Path(),
		FilePath: e.rel(start), LineStart: start.Line, LineEnd: end.Line, Source: source,
	})
}

func (e *extractor) emitFunc(p *packages.Package, d *ast.FuncDecl, src []byte) {
	fn, ok := p.TypesInfo.Defs[d.Name].(*types.Func)
	if !ok {
		return
	}
	owner := ownerFqn(fn)
	if owner == "" {
		return
	}
	mods := []string{visibility(fn.Name())}
	if fn.Type().(*types.Signature).Recv() == nil {
		mods = append(mods, "static")
	}
	start, end := p.Fset.Position(d.Pos()), p.Fset.Position(d.End())
	body := ""
	if start.Offset >= 0 && end.Offset <= len(src) && start.Offset < end.Offset {
		body = string(src[start.Offset:end.Offset])
	}
	doc := ""
	if d.Doc != nil {
		doc = d.Doc.Text()
	}
	m := e.method(fn, owner, start, end, mods, body, doc)
	if e.seenMethod[m.Fqn] {
		return // already read on an earlier platform, calls included
	}
	e.addMethod(m)
	if d.Body == nil {
		return
	}
	ast.Inspect(d.Body, func(n ast.Node) bool {
		call, ok := n.(*ast.CallExpr)
		if !ok {
			return true
		}
		if callee := calledFunc(p.TypesInfo, call.Fun); callee != nil {
			if cfqn := funcFqn(callee); cfqn != "" {
				e.doc.CallGraph = append(e.doc.CallGraph, Call{m.Fqn, cfqn, p.Fset.Position(call.Lparen).Line})
			}
		}
		return true
	})
}

func (e *extractor) method(fn *types.Func, owner string, start, end token.Position, mods []string, body, doc string) Method {
	sig := fn.Type().(*types.Signature)
	params := make([]Param, 0, sig.Params().Len())
	for i := 0; i < sig.Params().Len(); i++ {
		v := sig.Params().At(i)
		params = append(params, Param{Name: v.Name(), Type: paramType(sig, i), Annotations: []string{}})
	}
	return Method{
		Fqn: funcFqn(fn), Name: fn.Name(), ClassFqn: owner, ReturnType: resultType(sig),
		Parameters: params, Modifiers: mods, ThrowsTypes: []string{}, Annotations: []any{},
		FilePath: e.rel(start), LineStart: start.Line, LineEnd: end.Line,
		Body: body, Javadoc: doc, Source: source,
	}
}

// linkImplementations adds IMPLEMENTS for every project type that satisfies a
// project interface (directly or through its pointer), and OVERRIDES from the
// concrete method to the interface method it fulfils.
func (e *extractor) linkImplementations() {
	for _, t := range e.named {
		ptr := types.NewPointer(t)
		for _, iface := range e.interfaces {
			it := iface.Underlying().(*types.Interface)
			if !types.Implements(t, it) && !types.Implements(ptr, it) {
				continue
			}
			e.addInheritance(typeFqn(t), typeFqn(iface), "IMPLEMENTS")
			for i := 0; i < it.NumMethods(); i++ {
				im := it.Method(i)
				obj, _, _ := types.LookupFieldOrMethod(ptr, true, im.Pkg(), im.Name())
				impl, ok := obj.(*types.Func)
				if !ok {
					continue
				}
				if a, b := funcFqn(impl), funcFqn(im); a != "" && b != "" && a != b && e.addEdge("O|"+a+"|"+b) {
					e.doc.MethodOverrides = append(e.doc.MethodOverrides, Override{a, b})
				}
			}
		}
	}
}

// calledFunc returns the function or method a call expression binds to, or nil
// for calls through function values, conversions and builtins.
func calledFunc(info *types.Info, fun ast.Expr) *types.Func {
	switch f := ast.Unparen(fun).(type) {
	case *ast.Ident:
		fn, _ := info.Uses[f].(*types.Func)
		return fn
	case *ast.SelectorExpr:
		if sel, ok := info.Selections[f]; ok {
			fn, _ := sel.Obj().(*types.Func)
			return fn
		}
		fn, _ := info.Uses[f.Sel].(*types.Func) // qualified: pkg.Func
		return fn
	case *ast.IndexExpr: // generic instantiation f[T](...)
		return calledFunc(info, f.X)
	case *ast.IndexListExpr:
		return calledFunc(info, f.X)
	}
	return nil
}

// ownerFqn is the graph class that holds fn: its receiver's named type, or its package.
func ownerFqn(fn *types.Func) string {
	fn = fn.Origin()
	sig := fn.Type().(*types.Signature)
	if sig.Recv() == nil {
		if fn.Pkg() == nil {
			return ""
		}
		return fn.Pkg().Path()
	}
	if n := namedOf(sig.Recv().Type()); n != nil {
		return typeFqn(n)
	}
	return ""
}

func funcFqn(fn *types.Func) string {
	fn = fn.Origin()
	owner := ownerFqn(fn)
	if owner == "" {
		return ""
	}
	sig := fn.Type().(*types.Signature)
	ps := make([]string, sig.Params().Len())
	for i := range ps {
		ps[i] = paramType(sig, i)
	}
	return owner + "#" + fn.Name() + "(" + strings.Join(ps, ",") + ")"
}

func typeFqn(n *types.Named) string {
	obj := n.Origin().Obj()
	if obj.Pkg() == nil {
		return obj.Name() // error, comparable
	}
	return obj.Pkg().Path() + "." + obj.Name()
}

func namedOf(t types.Type) *types.Named {
	if p, ok := t.(*types.Pointer); ok {
		t = p.Elem()
	}
	if a, ok := t.(*types.Alias); ok {
		t = types.Unalias(a)
	}
	n, _ := t.(*types.Named)
	return n
}

// Full import paths: two packages may share a name (config, util), and the
// importer links a type to its Class by the full name.
func qualifier(p *types.Package) string { return p.Path() }

func typeStr(t types.Type) string { return types.TypeString(t, qualifier) }

func paramType(sig *types.Signature, i int) string {
	t := sig.Params().At(i).Type()
	if sig.Variadic() && i == sig.Params().Len()-1 {
		if s, ok := t.(*types.Slice); ok {
			return "..." + typeStr(s.Elem())
		}
	}
	return typeStr(t)
}

func resultType(sig *types.Signature) string {
	r := sig.Results()
	switch r.Len() {
	case 0:
		return "void"
	case 1:
		return typeStr(r.At(0).Type())
	case 2:
		// (T, error) is Go's usual "returns a T": record T so RETURNS links it.
		if types.Identical(r.At(1).Type(), types.Universe.Lookup("error").Type()) {
			return typeStr(r.At(0).Type())
		}
	}
	parts := make([]string, r.Len())
	for i := range parts {
		parts[i] = typeStr(r.At(i).Type())
	}
	return "(" + strings.Join(parts, ", ") + ")"
}

func visibility(name string) string {
	if token.IsExported(name) {
		return "public"
	}
	return "private"
}
