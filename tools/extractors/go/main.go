// Standalone Go → universal-SymbolGraph extractor.
//
// Second reference implementation of the same JSON contract the IntelliJ
// plugin emits for Java and the python_ast_extractor emits for Python — here
// using Go's native go/parser + go/ast (stdlib, no IDE, no plugin). The
// existing Python GraphLoader imports the output unchanged.
//
// Mapping Go → universal core:
//   package           -> Class {kind:"PACKAGE"}   (HAS_METHOD parent for funcs)
//   struct type       -> Class {kind:"STRUCT"}
//   interface type    -> Class {kind:"INTERFACE"}
//   struct field      -> Field
//   func (no recv)    -> Method (classFqn = package)
//   method (w/ recv)  -> Method (classFqn = receiver type)
//   embedded type     -> EXTENDS edge (Go embedding ~ inheritance)
//   call expression   -> CALLS edge (best-effort by name; go/types would make
//                        this 100% — see note below)
//
// Accuracy note: this reference uses go/ast only (structural). For the
// 100%-type-accurate tier, resolve calls via go/types + go/packages — same
// JSON out, source="TYPES" instead of "AST". Kept ast-only here so the file
// is a single self-contained `go run` with no module graph to load.
//
// Usage:
//   go run main.go <src_root> --name <project> > out.json
//   onelens import-graph out.json --graph <name> --backend falkordblite
package main

import (
	"encoding/json"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"strings"
)

const source = "AST"

type Class struct {
	Fqn, Name, Kind, PackageName, SuperClass, FilePath, EnclosingClass, Source string
	LineStart, LineEnd                                                         int
}
type Param struct {
	Name        string   `json:"name"`
	Type        string   `json:"type"`
	Annotations []string `json:"annotations"`
}
type Method struct {
	Fqn, Name, ClassFqn, ReturnType, FilePath, Source string
	Parameters                                        []Param
	Modifiers, ThrowsTypes                            []string
	Annotations                                       []map[string]string
	IsConstructor                                     bool
	LineStart, LineEnd                                int
}
type Field struct {
	Fqn, Name, ClassFqn, Type, FilePath, Source string
	LineStart                                   int
}
type Edge map[string]interface{}

type Doc struct {
	Version         string            `json:"version"`
	ExportType      string            `json:"exportType"`
	Project         map[string]string `json:"project"`
	Classes         []Class           `json:"classes"`
	Methods         []Method          `json:"methods"`
	Fields          []Field           `json:"fields"`
	CallGraph       []Edge            `json:"callGraph"`
	Inheritance     []Edge            `json:"inheritance"`
	MethodOverrides []Edge            `json:"methodOverrides"`
	Adapters        []string          `json:"adapters"`
}

type extractor struct {
	root string
	fset *token.FileSet
	doc  *Doc
}

func main() {
	args := os.Args[1:]
	if len(args) == 0 {
		os.Stderr.WriteString("usage: go run main.go <src_root> [--name X]\n")
		os.Exit(2)
	}
	root := args[0]
	name := filepath.Base(root)
	for i := 1; i < len(args)-1; i++ {
		if args[i] == "--name" {
			name = args[i+1]
		}
	}
	e := &extractor{root: root, fset: token.NewFileSet(), doc: &Doc{
		Version: "1.0", ExportType: "full", Project: map[string]string{"name": name},
		MethodOverrides: []Edge{}, Adapters: []string{"go-ast"},
	}}
	e.walk()
	enc := json.NewEncoder(os.Stdout)
	enc.Encode(e.doc)
}

func (e *extractor) walk() {
	filepath.Walk(e.root, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() {
			if info != nil && info.IsDir() {
				n := info.Name()
				if n == "vendor" || n == ".git" || strings.HasPrefix(n, "_") {
					return filepath.SkipDir
				}
			}
			return nil
		}
		if !strings.HasSuffix(path, ".go") || strings.HasSuffix(path, "_test.go") {
			return nil
		}
		f, perr := parser.ParseFile(e.fset, path, nil, 0)
		if perr != nil {
			return nil
		}
		e.emitFile(path, f)
		return nil
	})
}

func (e *extractor) rel(path string) string {
	r, err := filepath.Rel(e.root, path)
	if err != nil {
		return path
	}
	return r
}

func (e *extractor) emitFile(path string, f *ast.File) {
	rel := e.rel(path)
	pkg := f.Name.Name
	// One PACKAGE class node per package (deduped loosely by name+dir).
	pkgFqn := strings.ReplaceAll(filepath.Dir(rel), "/", ".") + "." + pkg
	pkgFqn = strings.TrimPrefix(pkgFqn, ".")
	e.doc.Classes = append(e.doc.Classes, Class{
		Fqn: pkgFqn, Name: pkg, Kind: "PACKAGE", FilePath: rel,
		LineStart: 1, LineEnd: 1, Source: source,
	})

	for _, decl := range f.Decls {
		switch d := decl.(type) {
		case *ast.GenDecl:
			for _, spec := range d.Specs {
				if ts, ok := spec.(*ast.TypeSpec); ok {
					e.emitType(rel, pkgFqn, ts)
				}
			}
		case *ast.FuncDecl:
			e.emitFunc(rel, pkgFqn, d)
		}
	}
}

func (e *extractor) emitType(rel, pkgFqn string, ts *ast.TypeSpec) {
	typeFqn := pkgFqn + "." + ts.Name.Name
	pos := e.fset.Position(ts.Pos())
	end := e.fset.Position(ts.End())
	switch t := ts.Type.(type) {
	case *ast.StructType:
		e.doc.Classes = append(e.doc.Classes, Class{
			Fqn: typeFqn, Name: ts.Name.Name, Kind: "STRUCT", PackageName: pkgFqn,
			FilePath: rel, LineStart: pos.Line, LineEnd: end.Line, Source: source,
		})
		for _, fld := range t.Fields.List {
			tn := typeString(fld.Type)
			if len(fld.Names) == 0 { // embedded field == Go "inheritance"
				e.doc.Inheritance = append(e.doc.Inheritance, Edge{
					"childFqn": typeFqn, "parentFqn": pkgFqn + "." + simpleName(tn),
					"relationType": "EXTENDS",
				})
				continue
			}
			for _, nm := range fld.Names {
				e.doc.Fields = append(e.doc.Fields, Field{
					Fqn: typeFqn + "#" + nm.Name, Name: nm.Name, ClassFqn: typeFqn,
					Type: tn, FilePath: rel,
					LineStart: e.fset.Position(nm.Pos()).Line, Source: source,
				})
			}
		}
	case *ast.InterfaceType:
		e.doc.Classes = append(e.doc.Classes, Class{
			Fqn: typeFqn, Name: ts.Name.Name, Kind: "INTERFACE", PackageName: pkgFqn,
			FilePath: rel, LineStart: pos.Line, LineEnd: end.Line, Source: source,
		})
		for _, m := range t.Methods.List {
			if len(m.Names) == 0 { // embedded interface
				e.doc.Inheritance = append(e.doc.Inheritance, Edge{
					"childFqn": typeFqn, "parentFqn": pkgFqn + "." + simpleName(typeString(m.Type)),
					"relationType": "IMPLEMENTS",
				})
			}
		}
	}
}

func (e *extractor) emitFunc(rel, pkgFqn string, d *ast.FuncDecl) {
	owner := pkgFqn
	if d.Recv != nil && len(d.Recv.List) > 0 {
		owner = pkgFqn + "." + simpleName(typeString(d.Recv.List[0].Type))
	}
	var params []Param
	if d.Type.Params != nil {
		for _, p := range d.Type.Params.List {
			tn := typeString(p.Type)
			if len(p.Names) == 0 {
				params = append(params, Param{Type: tn, Annotations: []string{}})
			}
			for _, nm := range p.Names {
				params = append(params, Param{Name: nm.Name, Type: tn, Annotations: []string{}})
			}
		}
	}
	sig := make([]string, 0, len(params))
	for _, p := range params {
		if p.Type != "" {
			sig = append(sig, p.Type)
		} else {
			sig = append(sig, p.Name)
		}
	}
	mFqn := owner + "#" + d.Name.Name + "(" + strings.Join(sig, ",") + ")"
	pos := e.fset.Position(d.Pos())
	end := e.fset.Position(d.End())
	e.doc.Methods = append(e.doc.Methods, Method{
		Fqn: mFqn, Name: d.Name.Name, ClassFqn: owner, Parameters: params,
		Modifiers: exported(d.Name.Name), ThrowsTypes: []string{},
		Annotations: []map[string]string{}, FilePath: rel,
		LineStart: pos.Line, LineEnd: end.Line, Source: source,
	})
	// Best-effort call edges by callee name.
	if d.Body != nil {
		ast.Inspect(d.Body, func(n ast.Node) bool {
			if call, ok := n.(*ast.CallExpr); ok {
				if name := calleeName(call.Fun); name != "" {
					e.doc.CallGraph = append(e.doc.CallGraph, Edge{
						"callerFqn": mFqn, "calleeName": name,
						"line": e.fset.Position(call.Pos()).Line,
					})
				}
			}
			return true
		})
	}
}

func exported(name string) []string {
	if len(name) > 0 && name[0] >= 'A' && name[0] <= 'Z' {
		return []string{"public"}
	}
	return []string{"private"}
}
func simpleName(t string) string {
	t = strings.TrimPrefix(t, "*")
	if i := strings.LastIndex(t, "."); i >= 0 {
		t = t[i+1:]
	}
	return t
}
func typeString(e ast.Expr) string {
	switch t := e.(type) {
	case *ast.Ident:
		return t.Name
	case *ast.StarExpr:
		return "*" + typeString(t.X)
	case *ast.SelectorExpr:
		return typeString(t.X) + "." + t.Sel.Name
	case *ast.ArrayType:
		return "[]" + typeString(t.Elt)
	case *ast.MapType:
		return "map[" + typeString(t.Key) + "]" + typeString(t.Value)
	default:
		return "any"
	}
}
func calleeName(fun ast.Expr) string {
	switch f := fun.(type) {
	case *ast.Ident:
		return f.Name
	case *ast.SelectorExpr:
		return f.Sel.Name
	}
	return ""
}
