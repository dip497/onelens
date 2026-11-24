// C# -> OneLens graph JSON, using Roslyn (the C# compiler's own semantic model).
//
// Every .csproj under <src_root> is evaluated by MSBuild (`dotnet msbuild -getItem`)
// for its exact source files, preprocessor symbols and resolved references, then
// compiled in memory with Roslyn. Each call resolves to the exact method the C#
// compiler binds. The output is the same JSON the IntelliJ plugin writes for Java.
//
// Old-style .NET Framework projects (packages.config, TargetFrameworkVersion v4.x)
// get their reference assemblies from the Microsoft.NETFramework.ReferenceAssemblies
// packages and their packages.config libraries from nuget.org, cached under
// --cache-dir. COM references cannot be resolved off Windows and are skipped.
//
// C# -> graph:
//   class / struct / interface / enum / record -> Class
//   field, property, event, enum member        -> Field
//   method, constructor, operator, accessor    -> Method (accessors only when they have a body)
//   invocation, `new`, base(...)/this(...),
//   method group, property with a body         -> CALLS
//   base class / interface                     -> EXTENDS / IMPLEMENTS
//   override, interface implementation         -> OVERRIDES
//   attribute                                  -> annotations (ANNOTATED_WITH)
//   ASP.NET Core [Http*] action                -> Endpoint + HANDLES
//
// Usage: dotnet run -- <src_root> [--name <graph>] [--cache-dir <dir>] [--offline] > out.json

using System.Diagnostics;
using System.IO.Compression;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

if (args.Length < 1)
{
    Console.Error.WriteLine("usage: CsharpExtractor <src_root> [--name <graph>] [--cache-dir <dir>] [--offline]");
    return 2;
}
var root = Path.GetFullPath(args[0]);
string name = Path.GetFileName(root.TrimEnd('/'));
string cache = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".onelens", "csharp-cache");
bool offline = false;
for (int i = 1; i < args.Length; i++)
{
    switch (args[i])
    {
        case "--name": name = args[++i]; break;
        case "--cache-dir": cache = Path.GetFullPath(args[++i]); break;
        case "--offline": offline = true; break;
    }
}
var x = new Extractor(root, name, cache, offline);
x.Run();
return 0;

sealed record ProjectInfo(
    string Path, string AssemblyName, bool Legacy, List<string> Sources, List<string> References,
    List<string> ProjectRefs, List<string> UnresolvedRefNames, List<string> Usings,
    string[] Defines, string LangVersion, bool Nullable, OutputKind Output);

sealed class Extractor
{
    const string Source = "TYPES";
    static readonly HashSet<string> SkipDirs = new(StringComparer.OrdinalIgnoreCase)
        { "bin", "obj", ".git", "node_modules", "packages", ".vs" };

    static readonly SymbolDisplayFormat TypeFmt = new(
        globalNamespaceStyle: SymbolDisplayGlobalNamespaceStyle.Omitted,
        typeQualificationStyle: SymbolDisplayTypeQualificationStyle.NameAndContainingTypesAndNamespaces,
        genericsOptions: SymbolDisplayGenericsOptions.IncludeTypeParameters,
        miscellaneousOptions: SymbolDisplayMiscellaneousOptions.UseSpecialTypes);

    static readonly SymbolDisplayFormat FqnFmt = new(
        globalNamespaceStyle: SymbolDisplayGlobalNamespaceStyle.Omitted,
        typeQualificationStyle: SymbolDisplayTypeQualificationStyle.NameAndContainingTypesAndNamespaces,
        genericsOptions: SymbolDisplayGenericsOptions.None);

    readonly string root, name, cache, nugetRoot;
    readonly bool offline;
    readonly string noComTargets;
    readonly JsonArray classes = new(), methods = new(), fields = new(), calls = new(),
        inheritance = new(), overrides = new(), annotations = new(), endpoints = new();
    readonly HashSet<string> seen = new();
    readonly Dictionary<string, ProjectInfo> projects = new();
    readonly Dictionary<string, CSharpCompilation> compiled = new();
    int typeErrors, unresolvedCalls, resolvedCalls;
    readonly List<string> notes = new();

    public Extractor(string root, string name, string cache, bool offline)
    {
        this.root = root; this.name = name; this.cache = cache; this.offline = offline;
        nugetRoot = Environment.GetEnvironmentVariable("NUGET_PACKAGES")
            ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".nuget", "packages");
        Directory.CreateDirectory(cache);
        noComTargets = Path.Combine(cache, "skip-com-references.targets");
        File.WriteAllText(noComTargets, "<Project><Target Name=\"ResolveComReferences\" /></Project>");
    }

    public void Run()
    {
        var projs = FindProjects(root);
        if (projs.Count == 0) throw new InvalidOperationException($"no .csproj under {root}");
        foreach (var p in projs)
        {
            try { projects[p] = Evaluate(p); }
            catch (Exception ex) { notes.Add($"{Rel(p)}: evaluation failed: {ex.Message}"); }
        }
        foreach (var p in projects.Keys.ToList()) Compile(p, new HashSet<string>());
        FindNameCollisions();
        foreach (var (path, comp) in compiled) Walk(projects[path], comp);

        var doc = new JsonObject
        {
            ["version"] = "1.0",
            ["exportType"] = "full",
            ["project"] = new JsonObject { ["name"] = name },
            ["classes"] = classes, ["methods"] = methods, ["fields"] = fields,
            ["callGraph"] = calls, ["inheritance"] = inheritance, ["methodOverrides"] = overrides,
            ["annotations"] = annotations,
            ["spring"] = new JsonObject { ["beans"] = new JsonArray(), ["endpoints"] = endpoints, ["injections"] = new JsonArray() },
            ["adapters"] = new JsonArray("csharp-roslyn"),
        };
        foreach (var n in notes) Console.Error.WriteLine("csharp-roslyn: " + n);
        Console.Error.WriteLine($"csharp-roslyn: {compiled.Count} projects, {classes.Count} classes, {methods.Count} methods, " +
            $"{fields.Count} fields, {calls.Count} calls ({resolvedCalls} resolved, {unresolvedCalls} unresolved), " +
            $"{inheritance.Count} inheritance, {overrides.Count} overrides, {endpoints.Count} endpoints, {typeErrors} compile errors");
        using var stdout = Console.OpenStandardOutput();
        using var w = new Utf8JsonWriter(stdout);
        doc.WriteTo(w);
    }

    // ---------------------------------------------------------------- MSBuild

    static List<string> FindProjects(string dir)
    {
        var found = new List<string>();
        foreach (var f in Directory.EnumerateFiles(dir, "*.csproj")) found.Add(Path.GetFullPath(f));
        foreach (var d in Directory.EnumerateDirectories(dir))
        {
            var n = Path.GetFileName(d);
            if (SkipDirs.Contains(n) || n.StartsWith('.')) continue;
            found.AddRange(FindProjects(d));
        }
        found.Sort(StringComparer.Ordinal);
        return found;
    }

    ProjectInfo Evaluate(string csproj)
    {
        var xml = XDocument.Load(csproj);
        bool legacy = xml.Root!.Attribute("Sdk") == null;
        string dir = Path.GetDirectoryName(csproj)!;
        var props = new List<string> { "-p:EnableWindowsTargeting=true", "-p:BuildProjectReferences=false", "-p:DesignTimeBuild=true" };
        if (legacy)
        {
            var tfv = xml.Descendants().FirstOrDefault(e => e.Name.LocalName == "TargetFrameworkVersion")?.Value ?? "v4.0";
            var refRoot = FrameworkReferenceRoot(tfv);
            if (refRoot != null) props.Add($"-p:TargetFrameworkRootPath={refRoot}");
            props.Add($"-p:CustomAfterMicrosoftCommonTargets={noComTargets}");
        }
        else
        {
            var multi = xml.Descendants().FirstOrDefault(e => e.Name.LocalName == "TargetFrameworks")?.Value;
            if (!string.IsNullOrWhiteSpace(multi)) props.Add($"-p:TargetFramework={multi.Split(';')[0].Trim()}");
            Dotnet(dir, ["restore", csproj, .. props.Where(p => !p.Contains("DesignTimeBuild"))]);
        }
        var json = Dotnet(dir, ["msbuild", csproj, "-t:FindReferenceAssembliesForReferences", .. props,
            "-getItem:Compile", "-getItem:ReferencePathWithRefAssemblies", "-getItem:Reference",
            "-getItem:ProjectReference", "-getItem:Using",
            "-getProperty:DefineConstants", "-getProperty:LangVersion", "-getProperty:Nullable",
            "-getProperty:AssemblyName", "-getProperty:OutputType"]);
        int brace = json.IndexOf('{');
        if (brace < 0) throw new InvalidOperationException(FirstError(json));
        var d = JsonNode.Parse(json[brace..])!;
        var items = d["Items"]!;
        var p = d["Properties"]!;
        IEnumerable<JsonNode> Items(string k) => items[k]?.AsArray().Where(n => n != null).Select(n => n!) ?? [];

        var sources = Items("Compile").Select(n => Path.GetFullPath(Path.Combine(dir, n["Identity"]!.GetValue<string>().Replace('\\', '/'))))
            .Where(File.Exists).Distinct().ToList();
        var refs = Items("ReferencePathWithRefAssemblies")
            .Where(n => n["ReferenceSourceTarget"]?.GetValue<string>() != "ProjectReference")
            .Select(n => n["Identity"]!.GetValue<string>()).Where(File.Exists).ToList();
        var got = new HashSet<string>(refs.Select(r => Path.GetFileNameWithoutExtension(r)), StringComparer.OrdinalIgnoreCase);
        var unresolved = Items("Reference").Select(n => n["Identity"]!.GetValue<string>().Split(',')[0].Trim())
            .Where(r => !got.Contains(r)).ToList();
        var projRefs = Items("ProjectReference")
            .Select(n => Path.GetFullPath(Path.Combine(dir, n["Identity"]!.GetValue<string>().Replace('\\', '/')))).ToList();
        var usings = Items("Using").Select(n =>
        {
            var id = n["Identity"]!.GetValue<string>();
            var alias = n["Alias"]?.GetValue<string>();
            var stat = n["Static"]?.GetValue<string>();
            return !string.IsNullOrEmpty(alias) ? $"global using {alias} = global::{id};"
                : string.Equals(stat, "true", StringComparison.OrdinalIgnoreCase) ? $"global using static global::{id};"
                : $"global using global::{id};";
        }).ToList();
        string Prop(string k) => p[k]?.GetValue<string>() ?? "";
        var asm = Prop("AssemblyName");
        if (asm == "") asm = Path.GetFileNameWithoutExtension(csproj);
        return new ProjectInfo(csproj, asm, legacy, sources, refs, projRefs, unresolved, usings,
            Prop("DefineConstants").Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries),
            Prop("LangVersion"), Prop("Nullable") is "enable" or "annotations",
            Prop("OutputType").ToLowerInvariant() switch
            {
                "exe" => OutputKind.ConsoleApplication,
                "winexe" => OutputKind.WindowsApplication,
                _ => OutputKind.DynamicallyLinkedLibrary,
            });
    }

    string? FrameworkReferenceRoot(string tfv)
    {
        var tfm = "net" + tfv.TrimStart('v').Replace(".", "");
        var pkg = Path.Combine(nugetRoot, "microsoft.netframework.referenceassemblies." + tfm);
        if (!Directory.Exists(pkg))
        {
            var helper = Path.Combine(cache, "refasm-" + tfm);
            Directory.CreateDirectory(helper);
            File.WriteAllText(Path.Combine(helper, "refasm.csproj"),
                $"<Project Sdk=\"Microsoft.NET.Sdk\"><PropertyGroup><TargetFramework>{tfm}</TargetFramework></PropertyGroup></Project>");
            Dotnet(helper, ["restore"]);
        }
        var build = Directory.Exists(pkg) ? Directory.GetDirectories(pkg).OrderBy(s => s).Select(v => Path.Combine(v, "build")).LastOrDefault() : null;
        if (build == null) notes.Add($"no reference assemblies for {tfv}");
        return build;
    }

    static string Dotnet(string cwd, string[] argv)
    {
        var psi = new ProcessStartInfo("dotnet") { WorkingDirectory = cwd, RedirectStandardOutput = true, RedirectStandardError = true };
        foreach (var a in argv) psi.ArgumentList.Add(a);
        psi.Environment["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1";
        psi.Environment["DOTNET_NOLOGO"] = "1";
        psi.Environment["MSBUILDDISABLENODEREUSE"] = "1";
        using var proc = Process.Start(psi)!;
        var errTask = proc.StandardError.ReadToEndAsync();
        var output = proc.StandardOutput.ReadToEnd();
        proc.WaitForExit();
        return output.Contains('{') ? output : output + errTask.Result;
    }

    static string FirstError(string output) =>
        output.Split('\n').FirstOrDefault(l => l.Contains("error")) ?? output.Trim().Split('\n').LastOrDefault() ?? "no output";

    // ------------------------------------------------------- legacy packages

    List<string> LegacyPackageRefs(ProjectInfo p, Dictionary<string, string> projectAssemblies)
    {
        var wanted = p.UnresolvedRefNames.Where(r => !projectAssemblies.ContainsKey(r)).ToList();
        if (wanted.Count == 0 || offline) return [];
        var dir = Path.GetDirectoryName(p.Path)!;
        var cfg = Path.Combine(dir, "packages.config");
        var packages = new List<(string id, string version)>();
        if (File.Exists(cfg))
            packages.AddRange(XDocument.Load(cfg).Descendants("package")
                .Select(e => (e.Attribute("id")!.Value, e.Attribute("version")!.Value)));
        var found = new List<string>();
        foreach (var refName in wanted)
        {
            string? dll = null;
            foreach (var (id, ver) in packages)
                if ((dll = FindDll(FetchPackage(id, ver), refName)) != null) break;
            if (dll == null)
            {
                var ver = LatestVersion(refName);
                if (ver != null) dll = FindDll(FetchPackage(refName, ver), refName);
            }
            if (dll != null) found.Add(dll);
            else notes.Add($"{Rel(p.Path)}: reference {refName} not found (calls into it stay unresolved)");
        }
        return found;
    }

    static readonly HttpClient http = new() { Timeout = TimeSpan.FromMinutes(2) };

    string? FetchPackage(string id, string version)
    {
        var dest = Path.Combine(cache, "packages", (id + "." + version).ToLowerInvariant());
        if (Directory.Exists(dest)) return dest;
        try
        {
            var url = $"https://api.nuget.org/v3-flatcontainer/{id.ToLowerInvariant()}/{version.ToLowerInvariant()}/{id.ToLowerInvariant()}.{version.ToLowerInvariant()}.nupkg";
            var bytes = http.GetByteArrayAsync(url).GetAwaiter().GetResult();
            var tmp = dest + ".tmp";
            if (Directory.Exists(tmp)) Directory.Delete(tmp, true);
            using (var zip = new ZipArchive(new MemoryStream(bytes)))
                foreach (var e in zip.Entries.Where(e => e.FullName.StartsWith("lib/", StringComparison.OrdinalIgnoreCase)
                                                        && e.FullName.EndsWith(".dll", StringComparison.OrdinalIgnoreCase)))
                {
                    var target = Path.GetFullPath(Path.Combine(tmp, e.FullName));
                    if (!target.StartsWith(Path.GetFullPath(tmp) + Path.DirectorySeparatorChar)) continue;
                    Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                    e.ExtractToFile(target, true);
                }
            Directory.CreateDirectory(tmp);
            Directory.Move(tmp, dest);
            return dest;
        }
        catch { return null; }
    }

    string? LatestVersion(string id)
    {
        try
        {
            var json = http.GetStringAsync($"https://api.nuget.org/v3-flatcontainer/{id.ToLowerInvariant()}/index.json").GetAwaiter().GetResult();
            return JsonNode.Parse(json)!["versions"]!.AsArray().Select(v => v!.GetValue<string>()).LastOrDefault(v => !v.Contains('-'));
        }
        catch { return null; }
    }

    static string? FindDll(string? pkgDir, string refName)
    {
        if (pkgDir == null || !Directory.Exists(pkgDir)) return null;
        var dlls = Directory.GetFiles(pkgDir, refName + ".dll", SearchOption.AllDirectories);
        static int Rank(string path)
        {
            var fw = path.Replace('\\', '/').Split('/').Reverse().Skip(1).First().ToLowerInvariant();
            if (fw.StartsWith("net40")) return 0;
            if (fw.StartsWith("net35") || fw.StartsWith("net20") || fw.StartsWith("net2")) return 1;
            if (fw.StartsWith("net4")) return 2;
            if (fw.StartsWith("netstandard")) return 3;
            return 4;
        }
        return dlls.OrderBy(Rank).ThenBy(s => s).FirstOrDefault();
    }

    // --------------------------------------------------------------- compile

    CSharpCompilation? Compile(string path, HashSet<string> visiting)
    {
        if (compiled.TryGetValue(path, out var done)) return done;
        if (!projects.TryGetValue(path, out var p) || !visiting.Add(path)) return null;
        var byAssembly = projects.Values.GroupBy(v => v.AssemblyName, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(g => g.Key, g => g.First().Path, StringComparer.OrdinalIgnoreCase);

        var refs = new List<MetadataReference>();
        foreach (var r in p.References) refs.Add(MetadataReference.CreateFromFile(r));
        var deps = p.ProjectRefs.Concat(p.UnresolvedRefNames.Where(byAssembly.ContainsKey).Select(n => byAssembly[n]))
            .Where(d => d != path).Distinct();
        foreach (var dep in deps)
            if (Compile(dep, visiting) is { } c) refs.Add(c.ToMetadataReference());
        if (p.Legacy)
            foreach (var dll in LegacyPackageRefs(p, byAssembly)) refs.Add(MetadataReference.CreateFromFile(dll));

        var lang = LanguageVersion.Latest;
        if (p.LangVersion != "" && !LanguageVersionFacts.TryParse(p.LangVersion, out lang)) lang = LanguageVersion.Latest;
        var parse = new CSharpParseOptions(lang, DocumentationMode.Parse, SourceCodeKind.Regular, p.Defines);
        var trees = p.Sources.Select(f => CSharpSyntaxTree.ParseText(File.ReadAllText(f), parse, f, Encoding.UTF8)).ToList();
        if (p.Usings.Count > 0)
            trees.Add(CSharpSyntaxTree.ParseText(string.Join("\n", p.Usings), parse, Path.Combine(Path.GetDirectoryName(path)!, "obj", "GlobalUsings.g.cs")));
        var opts = new CSharpCompilationOptions(p.Output, allowUnsafe: true,
            nullableContextOptions: p.Nullable ? NullableContextOptions.Enable : NullableContextOptions.Disable);
        var comp = CSharpCompilation.Create(p.AssemblyName, trees, refs, opts);
        var errors = comp.GetDiagnostics().Count(d => d.Severity == DiagnosticSeverity.Error);
        typeErrors += errors;
        if (Environment.GetEnvironmentVariable("ONELENS_CSHARP_DIAGNOSTICS") == "1")
            foreach (var d in comp.GetDiagnostics().Where(d => d.Severity == DiagnosticSeverity.Error).Take(20))
                notes.Add($"{Rel(path)}: {d}");
        notes.Add($"{Rel(path)}: {p.Sources.Count} files, {p.References.Count} references, {errors} compile errors");
        compiled[path] = comp;
        visiting.Remove(path);
        return comp;
    }

    // ------------------------------------------------------------------ walk

    // Two projects that each declare `Program` (or any same-named type in a different
    // file) would merge into one node. Those types get their assembly name in front:
    // `mtPoller.Program`, `PollerUI.Program`. A file shared by two projects stays one node.
    void FindNameCollisions()
    {
        var files = new Dictionary<string, HashSet<string>>();
        var assemblies = new Dictionary<string, HashSet<string>>();
        foreach (var (path, comp) in compiled)
            foreach (var tree in comp.SyntaxTrees.Where(t => projects[path].Sources.Contains(t.FilePath)))
            {
                var model = comp.GetSemanticModel(tree);
                var declared = tree.GetRoot().DescendantNodes().OfType<BaseTypeDeclarationSyntax>()
                    .Select(d => model.GetDeclaredSymbol(d) as INamedTypeSymbol)
                    .Append(TopLevelMain(tree, model)?.ContainingType);
                foreach (var t in declared)
                    if (t != null)
                    {
                        var fqn = t.OriginalDefinition.ToDisplayString(FqnFmt);
                        if (!files.ContainsKey(fqn)) { files[fqn] = new(); assemblies[fqn] = new(); }
                        files[fqn].Add(tree.FilePath);
                        assemblies[fqn].Add(comp.AssemblyName!);
                    }
            }
        foreach (var fqn in files.Keys)
            if (files[fqn].Count > 1 && assemblies[fqn].Count > 1) Collisions.Add(fqn);
        if (Collisions.Count > 0) notes.Add($"{Collisions.Count} type names declared in more than one project, prefixed with the assembly name: {string.Join(", ", Collisions.Take(10))}");
    }

    void Walk(ProjectInfo p, CSharpCompilation comp)
    {
        foreach (var tree in comp.SyntaxTrees)
        {
            if (!p.Sources.Contains(tree.FilePath)) continue;
            var model = comp.GetSemanticModel(tree);
            foreach (var decl in tree.GetRoot().DescendantNodes().OfType<BaseTypeDeclarationSyntax>())
                if (model.GetDeclaredSymbol(decl) is INamedTypeSymbol t) EmitType(t, decl, model);
            if (TopLevelMain(tree, model) is { } main) EmitTopLevelProgram(main, (CompilationUnitSyntax)tree.GetRoot(), model);
        }
    }

    // Top-level statements (`var builder = WebApplication.CreateBuilder(args); ...`) compile
    // to an implicit `Program.<Main>$`; it has no class declaration, so it is emitted here.
    static IMethodSymbol? TopLevelMain(SyntaxTree tree, SemanticModel model) =>
        tree.GetRoot() is CompilationUnitSyntax cu && cu.Members.Any(m => m is GlobalStatementSyntax)
            ? model.GetDeclaredSymbol(cu) as IMethodSymbol : null;

    void EmitTopLevelProgram(IMethodSymbol main, CompilationUnitSyntax cu, SemanticModel model)
    {
        var owner = TypeFqn(main.ContainingType);
        var span = cu.GetLocation().GetLineSpan();
        if (seen.Add("C|" + owner))
            classes.Add(new JsonObject
            {
                ["fqn"] = owner, ["name"] = main.ContainingType.Name, ["kind"] = "CLASS", ["packageName"] = "",
                ["superClass"] = "", ["enclosingClass"] = "", ["filePath"] = Rel(span.Path),
                ["lineStart"] = 1, ["lineEnd"] = span.EndLinePosition.Line + 1,
                ["modifiers"] = new JsonArray("internal", "static"), ["annotations"] = new JsonArray(),
                ["javadoc"] = "", ["source"] = Source,
            });
        EmitMethod(main, cu, model, cu.Members.OfType<GlobalStatementSyntax>().ToArray());
    }

    void EmitType(INamedTypeSymbol t, BaseTypeDeclarationSyntax decl, SemanticModel model)
    {
        var fqn = TypeFqn(t);
        if (seen.Add("C|" + fqn))
        {
            var main = PrimaryDeclaration(t) ?? decl;
            var ms = main.GetLocation().GetLineSpan();
            var baseType = t.BaseType is { SpecialType: SpecialType.None } b && b.TypeKind != TypeKind.Error ? TypeFqn(b) : "";
            classes.Add(new JsonObject
            {
                ["fqn"] = fqn, ["name"] = t.Name, ["kind"] = Kind(t),
                ["packageName"] = t.ContainingNamespace.IsGlobalNamespace ? "" : t.ContainingNamespace.ToDisplayString(),
                ["superClass"] = baseType,
                ["enclosingClass"] = t.ContainingType != null ? TypeFqn(t.ContainingType) : "",
                ["filePath"] = Rel(ms.Path), ["lineStart"] = ms.StartLinePosition.Line + 1, ["lineEnd"] = ms.EndLinePosition.Line + 1,
                ["modifiers"] = new JsonArray(Modifiers(t).Select(m => (JsonNode)m!).ToArray()),
                ["annotations"] = AnnotationRefs(t),
                ["javadoc"] = Doc(main),
                ["source"] = Source,
            });
            if (baseType != "") AddInheritance(fqn, baseType, "EXTENDS");
            foreach (var i in t.Interfaces.Where(i => i.TypeKind != TypeKind.Error))
                AddInheritance(fqn, TypeFqn(i), t.TypeKind == TypeKind.Interface ? "EXTENDS" : "IMPLEMENTS");
            EmitAttributes(t, fqn, "CLASS");
            LinkInterfaceImplementations(t);
        }

        if (decl is EnumDeclarationSyntax en)
        {
            foreach (var m in en.Members)
                if (model.GetDeclaredSymbol(m) is { } f) EmitField(f, fqn, m, fqn);
            return;
        }
        var td = (TypeDeclarationSyntax)decl;
        foreach (var member in td.Members)
        {
            switch (member)
            {
                case BaseMethodDeclarationSyntax bm when model.GetDeclaredSymbol(bm) is IMethodSymbol ms:
                    EmitMethod(ms, bm, model, bm.Body, bm.ExpressionBody, (bm as ConstructorDeclarationSyntax)?.Initializer);
                    break;
                case BasePropertyDeclarationSyntax bp when model.GetDeclaredSymbol(bp) is ISymbol ps:
                    if (ps is IPropertySymbol or IEventSymbol && bp is not IndexerDeclarationSyntax)
                        EmitField(ps, fqn, bp, ps is IPropertySymbol pp ? pp.Type.ToDisplayString(TypeFmt) : ((IEventSymbol)ps).Type.ToDisplayString(TypeFmt));
                    if (bp is PropertyDeclarationSyntax { ExpressionBody: { } eb } && ps is IPropertySymbol { GetMethod: { } g })
                        EmitMethod(g, bp, model, eb);
                    foreach (var acc in bp.AccessorList?.Accessors ?? default)
                        if ((acc.Body != null || acc.ExpressionBody != null) && model.GetDeclaredSymbol(acc) is IMethodSymbol am)
                            EmitMethod(am, acc, model, acc.Body, acc.ExpressionBody);
                    break;
                case BaseFieldDeclarationSyntax bf:
                    foreach (var v in bf.Declaration.Variables)
                        if (model.GetDeclaredSymbol(v) is { } fs)
                            EmitField(fs, fqn, v, (fs is IFieldSymbol ft ? ft.Type : ((IEventSymbol)fs).Type).ToDisplayString(TypeFmt));
                    break;
            }
        }
        if (td is ClassDeclarationSyntax or RecordDeclarationSyntax && td.ParameterList != null
            && t.InstanceConstructors.FirstOrDefault(c => c.Parameters.Length == td.ParameterList.Parameters.Count) is { } primary)
            EmitMethod(primary, td.ParameterList, model, td.BaseList);
    }

    void EmitField(ISymbol f, string owner, SyntaxNode node, string type)
    {
        var ffqn = owner + "#" + f.Name;
        if (!seen.Add("F|" + ffqn)) return;
        var line = node.GetLocation().GetLineSpan();
        fields.Add(new JsonObject
        {
            ["fqn"] = ffqn, ["name"] = f.Name, ["classFqn"] = owner, ["type"] = type,
            ["modifiers"] = new JsonArray(Modifiers(f).Select(m => (JsonNode)m!).ToArray()),
            ["filePath"] = Rel(line.Path), ["lineStart"] = line.StartLinePosition.Line + 1, ["source"] = Source,
        });
        EmitAttributes(f, ffqn, "FIELD");
    }

    void EmitMethod(IMethodSymbol m, SyntaxNode decl, SemanticModel model, params SyntaxNode?[] scope)
    {
        bool hasBody = scope.Any(s => s is BlockSyntax or ArrowExpressionClauseSyntax);
        var mfqn = MethodFqn(m);
        if (mfqn == null || !seen.Add("M|" + mfqn)) return;
        var span = decl.GetLocation().GetLineSpan();
        var mods = Modifiers(m);
        if (m.ContainingType.TypeKind == TypeKind.Interface && !hasBody && !mods.Contains("abstract")) mods.Add("abstract");
        methods.Add(new JsonObject
        {
            ["fqn"] = mfqn, ["name"] = MethodName(m), ["classFqn"] = TypeFqn(m.ContainingType),
            ["returnType"] = m.MethodKind is MethodKind.Constructor or MethodKind.StaticConstructor ? "" : m.ReturnType.ToDisplayString(TypeFmt),
            ["parameters"] = new JsonArray(m.Parameters.Select(p => (JsonNode)new JsonObject
            {
                ["name"] = p.Name, ["type"] = p.Type.ToDisplayString(TypeFmt), ["annotations"] = new JsonArray(),
            }).ToArray()),
            ["modifiers"] = new JsonArray(mods.Select(x => (JsonNode)x!).ToArray()),
            ["throwsTypes"] = new JsonArray(),
            ["annotations"] = AnnotationRefs(m),
            ["isConstructor"] = m.MethodKind is MethodKind.Constructor or MethodKind.StaticConstructor,
            ["filePath"] = Rel(span.Path), ["lineStart"] = span.StartLinePosition.Line + 1, ["lineEnd"] = span.EndLinePosition.Line + 1,
            ["body"] = decl.ToString(), ["javadoc"] = Doc(decl), ["source"] = Source,
        });
        EmitAttributes(m, mfqn, "METHOD");
        EmitEndpoint(m, mfqn);
        if (m.OverriddenMethod is { } over && MethodFqn(over) is { } ofqn) AddOverride(mfqn, ofqn);

        foreach (var s in scope.OfType<SyntaxNode>())
            foreach (var n in s.DescendantNodesAndSelf())
                CallFrom(mfqn, n, model);
    }

    void CallFrom(string caller, SyntaxNode n, SemanticModel model)
    {
        ISymbol? target = null;
        switch (n)
        {
            case InvocationExpressionSyntax inv:
                target = Resolve(model, inv);
                if (target == null) { unresolvedCalls++; return; }
                break;
            case BaseObjectCreationExpressionSyntax oc:
                target = Resolve(model, oc);
                if (target == null) { unresolvedCalls++; return; }
                break;
            case ConstructorInitializerSyntax ci:
                target = Resolve(model, ci);
                break;
            case PrimaryConstructorBaseTypeSyntax pc:
                target = Resolve(model, pc);
                break;
            case IdentifierNameSyntax or MemberAccessExpressionSyntax:
                if (n.Parent is MemberAccessExpressionSyntax ma && ma.Name == n) return; // the member access is visited itself
                if (n.Parent is InvocationExpressionSyntax pi && pi.Expression == n) return; // counted as the invocation
                var sym = model.GetSymbolInfo(n).Symbol;
                if (sym is IMethodSymbol { MethodKind: MethodKind.Ordinary } mg) target = mg; // method group: handler, delegate
                else if (sym is IPropertySymbol prop && HasBody(prop, n)) target = IsWrite(n) ? prop.SetMethod : prop.GetMethod;
                else return;
                break;
            default:
                return;
        }
        if (target is not IMethodSymbol callee || MethodFqn(callee) is not { } cfqn) return;
        resolvedCalls++;
        calls.Add(new JsonObject { ["callerFqn"] = caller, ["calleeFqn"] = cfqn, ["line"] = n.GetLocation().GetLineSpan().StartLinePosition.Line + 1 });
    }

    static ISymbol? Resolve(SemanticModel model, SyntaxNode n)
    {
        var info = model.GetSymbolInfo(n);
        if (info.Symbol != null) return info.Symbol;
        return info.CandidateSymbols.Length == 1 ? info.CandidateSymbols[0] : null;
    }

    static bool HasBody(IPropertySymbol p, SyntaxNode use)
    {
        var acc = IsWrite(use) ? p.SetMethod : p.GetMethod;
        if (acc == null) return false;
        foreach (var r in acc.DeclaringSyntaxReferences)
            if (r.GetSyntax() is AccessorDeclarationSyntax { Body: not null } or AccessorDeclarationSyntax { ExpressionBody: not null }
                or ArrowExpressionClauseSyntax) return true;
        return false;
    }

    static bool IsWrite(SyntaxNode n)
    {
        var node = n.Parent is MemberAccessExpressionSyntax ma && ma.Name == n ? ma : n;
        return node.Parent is AssignmentExpressionSyntax a && a.Left == node;
    }

    void LinkInterfaceImplementations(INamedTypeSymbol t)
    {
        if (t.TypeKind is TypeKind.Interface or TypeKind.Enum) return;
        foreach (var iface in t.AllInterfaces)
            foreach (var im in iface.GetMembers().OfType<IMethodSymbol>())
            {
                if (t.FindImplementationForInterfaceMember(im) is not IMethodSymbol impl) continue;
                if (!SymbolEqualityComparer.Default.Equals(impl.ContainingType.OriginalDefinition, t.OriginalDefinition)) continue;
                if (MethodFqn(impl) is { } a && MethodFqn(im) is { } b && a != b) AddOverride(a, b);
            }
    }

    void EmitEndpoint(IMethodSymbol m, string mfqn)
    {
        var verbs = m.GetAttributes().Select(a => (a, n: a.AttributeClass?.Name ?? ""))
            .Where(x => Regex.IsMatch(x.n, "^Http(Get|Post|Put|Delete|Patch|Head|Options)Attribute$")).ToList();
        if (verbs.Count == 0) return;
        var type = m.ContainingType;
        var controller = type.Name.EndsWith("Controller") ? type.Name[..^"Controller".Length] : type.Name;
        var classRoute = RouteTemplate(type.GetAttributes(), "RouteAttribute") ?? "";
        var methodRoute = RouteTemplate(m.GetAttributes(), "RouteAttribute");
        foreach (var (a, n) in verbs)
        {
            var verb = n[4..^"Attribute".Length].ToUpperInvariant();
            var tmpl = a.ConstructorArguments.FirstOrDefault().Value as string ?? methodRoute ?? "";
            var path = tmpl.StartsWith('/') || tmpl.StartsWith("~/") ? tmpl.TrimStart('~') : "/" + string.Join('/', new[] { classRoute, tmpl }.Where(s => s != "").Select(s => s.Trim('/')));
            path = path.Replace("[controller]", controller, StringComparison.OrdinalIgnoreCase).Replace("[action]", m.Name, StringComparison.OrdinalIgnoreCase);
            if (!seen.Add("E|" + verb + ":" + path)) continue;
            endpoints.Add(new JsonObject
            {
                ["path"] = path, ["httpMethod"] = verb, ["controllerFqn"] = TypeFqn(type), ["handlerMethodFqn"] = mfqn,
            });
        }
    }

    static string? RouteTemplate(IEnumerable<AttributeData> attrs, string attr) =>
        attrs.FirstOrDefault(a => a.AttributeClass?.Name == attr)?.ConstructorArguments.FirstOrDefault().Value as string;

    void EmitAttributes(ISymbol s, string target, string kind)
    {
        foreach (var a in s.GetAttributes())
        {
            if (a.AttributeClass is not { TypeKind: not TypeKind.Error } ac) continue;
            var values = new JsonObject();
            var flat = new JsonObject();
            for (int i = 0; i < a.ConstructorArguments.Length; i++)
            {
                var key = i == 0 ? "value" : "arg" + i;
                values[key] = ConstantText(a.ConstructorArguments[i]);
                if (a.ConstructorArguments[i].Kind != TypedConstantKind.Array) flat[key] = ConstantText(a.ConstructorArguments[i]);
            }
            foreach (var (k, v) in a.NamedArguments)
            {
                values[k] = ConstantText(v);
                if (v.Kind != TypedConstantKind.Array) flat[k] = ConstantText(v);
            }
            annotations.Add(new JsonObject
            {
                ["targetFqn"] = target, ["targetKind"] = kind, ["annotationFqn"] = TypeFqn(ac),
                ["attributes"] = values.ToJsonString(), ["attrValues"] = flat,
            });
        }
    }

    static string ConstantText(TypedConstant c) => c.IsNull ? "" : c.Kind switch
    {
        TypedConstantKind.Array => "[" + string.Join(",", c.Values.Select(ConstantText)) + "]",
        TypedConstantKind.Type => (c.Value as ITypeSymbol)?.ToDisplayString(FqnFmt) ?? "",
        TypedConstantKind.Enum => c.Type!.GetMembers().OfType<IFieldSymbol>().FirstOrDefault(f => Equals(f.ConstantValue, c.Value))?.Name ?? c.Value?.ToString() ?? "",
        _ => c.Value?.ToString() ?? "",
    };

    static JsonArray AnnotationRefs(ISymbol s) => new(s.GetAttributes()
        .Where(a => a.AttributeClass is { TypeKind: not TypeKind.Error })
        .Select(a => (JsonNode)new JsonObject { ["fqn"] = TypeFqn(a.AttributeClass!), ["name"] = a.AttributeClass!.Name }).ToArray());

    void AddInheritance(string child, string parent, string relation)
    {
        if (seen.Add($"I|{child}|{parent}|{relation}"))
            inheritance.Add(new JsonObject { ["childFqn"] = child, ["parentFqn"] = parent, ["relationType"] = relation });
    }

    void AddOverride(string method, string overridden)
    {
        if (seen.Add($"O|{method}|{overridden}"))
            overrides.Add(new JsonObject { ["methodFqn"] = method, ["overridesFqn"] = overridden });
    }

    // ----------------------------------------------------------------- names

    static readonly HashSet<string> Collisions = new();

    static string TypeFqn(INamedTypeSymbol t)
    {
        var fqn = t.OriginalDefinition.ToDisplayString(FqnFmt);
        return Collisions.Contains(fqn) && t.Locations.Any(l => l.IsInSource) ? t.ContainingAssembly.Name + "." + fqn : fqn;
    }

    static string? MethodFqn(IMethodSymbol m)
    {
        m = (m.ReducedFrom ?? m).OriginalDefinition;
        if (m.MethodKind is MethodKind.LocalFunction or MethodKind.AnonymousFunction or MethodKind.DelegateInvoke) return null;
        if (m.ContainingType is not { TypeKind: not TypeKind.Error } owner) return null;
        var ps = string.Join(",", m.Parameters.Select(p => RefPrefix(p) + p.Type.ToDisplayString(TypeFmt)));
        return TypeFqn(owner) + "#" + MethodName(m) + "(" + ps + ")";
    }

    static string MethodName(IMethodSymbol m) => m.MethodKind switch
    {
        MethodKind.Constructor => m.ContainingType.Name,
        MethodKind.StaticConstructor => ".cctor",
        _ => m.Name,
    };

    static string RefPrefix(IParameterSymbol p) => p.RefKind switch
    {
        RefKind.Ref => "ref ", RefKind.Out => "out ", RefKind.In => "in ", _ => "",
    };

    static string Kind(INamedTypeSymbol t) => t.TypeKind switch
    {
        TypeKind.Interface => "INTERFACE",
        TypeKind.Enum => "ENUM",
        TypeKind.Struct => t.IsRecord ? "RECORD" : "STRUCT",
        _ => t.IsRecord ? "RECORD" : t.IsAbstract ? "ABSTRACT_CLASS" : "CLASS",
    };

    static List<string> Modifiers(ISymbol s)
    {
        var mods = new List<string>
        {
            s.DeclaredAccessibility switch
            {
                Accessibility.Public => "public",
                Accessibility.Private => "private",
                Accessibility.Protected or Accessibility.ProtectedOrInternal or Accessibility.ProtectedAndInternal => "protected",
                _ => "internal",
            },
        };
        if (s.IsStatic) mods.Add("static");
        if (s.IsAbstract) mods.Add("abstract");
        if (s.IsVirtual) mods.Add("virtual");
        if (s.IsOverride) mods.Add("override");
        if (s.IsSealed) mods.Add("sealed");
        if (s is IMethodSymbol { IsAsync: true }) mods.Add("async");
        return mods;
    }

    static BaseTypeDeclarationSyntax? PrimaryDeclaration(INamedTypeSymbol t) =>
        t.DeclaringSyntaxReferences.Select(r => r.GetSyntax()).OfType<BaseTypeDeclarationSyntax>()
            .OrderBy(d => d.SyntaxTree.FilePath.EndsWith(".Designer.cs", StringComparison.OrdinalIgnoreCase) ? 1 : 0)
            .FirstOrDefault();

    static string Doc(SyntaxNode node)
    {
        var lines = node.GetLeadingTrivia()
            .Where(t => t.IsKind(SyntaxKind.SingleLineDocumentationCommentTrivia) || t.IsKind(SyntaxKind.MultiLineDocumentationCommentTrivia))
            .SelectMany(t => t.ToFullString().Split('\n'))
            .Select(l => Regex.Replace(l.Trim().TrimStart('/').Trim(), "<[^>]+>", "").Trim())
            .Where(l => l != "");
        return string.Join("\n", lines);
    }

    string Rel(string path) => Path.GetRelativePath(root, path).Replace('\\', '/');
}
