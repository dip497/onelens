// Type-resolved OneLens export for Dart and Flutter projects.
//
//   dart run bin/dart_extractor.dart <project_root> [--name <graph>] [--out <file>]
//
// Every call edge comes from the element the analyzer resolved for that call
// site (the same engine behind the Dart analysis server and the IDE plugins).
// The project must have been prepared with `flutter pub get` / `dart pub get`
// so `.dart_tool/package_config.json` exists.

import 'dart:convert';
import 'dart:io';

import 'package:analyzer/dart/analysis/analysis_context_collection.dart';
import 'package:analyzer/dart/analysis/results.dart';
import 'package:analyzer/dart/ast/ast.dart';
import 'package:analyzer/dart/ast/visitor.dart';
import 'package:analyzer/dart/element/element.dart';
import 'package:analyzer/dart/element/type.dart';
import 'package:analyzer/error/error.dart';
import 'package:path/path.dart' as p;

const httpVerbs = {'get', 'post', 'put', 'patch', 'delete', 'head'};
const urlParamNames = {'url', 'path', 'uri', 'endpoint'};

Future<void> main(List<String> args) async {
  if (args.isEmpty) {
    stderr.writeln('usage: dart_extractor <project_root> [--name <graph>] [--out <file>]');
    exit(2);
  }
  final root = p.normalize(p.absolute(args[0]));
  var name = p.basename(root);
  String? out;
  for (var i = 1; i < args.length - 1; i++) {
    if (args[i] == '--name') name = args[i + 1];
    if (args[i] == '--out') out = args[i + 1];
  }
  if (!File(p.join(root, '.dart_tool', 'package_config.json')).existsSync()) {
    stderr.writeln('missing .dart_tool/package_config.json: run `flutter pub get` in $root first');
    exit(2);
  }

  final extractor = Extractor(root);
  final dirs = ['lib', 'bin', 'test']
      .map((d) => p.join(root, d))
      .where((d) => Directory(d).existsSync())
      .toList();
  final collection = AnalysisContextCollection(
    includedPaths: dirs,
    sdkPath: dartSdk(),
  );
  var files = 0, errors = 0;
  for (final context in collection.contexts) {
    final paths = context.contextRoot.analyzedFiles().where((f) => f.endsWith('.dart')).toList()..sort();
    for (final path in paths) {
      final result = await context.currentSession.getResolvedUnit(path);
      if (result is! ResolvedUnitResult) continue;
      files++;
      final unitErrors = result.diagnostics.where((d) => d.diagnosticCode.type == DiagnosticType.COMPILE_TIME_ERROR).toList();
      errors += unitErrors.length;
      if (Platform.environment['ONELENS_DART_DIAGNOSTICS'] == '1') {
        for (final d in unitErrors.take(5)) {
          stderr.writeln('${p.relative(path, from: root)}:${result.lineInfo.getLocation(d.offset).lineNumber} ${d.message}');
        }
      }
      extractor.unit(result);
    }
  }

  final doc = extractor.document(name);
  final json = jsonEncode(doc);
  if (out == null) {
    stdout.write(json);
  } else {
    File(out).writeAsStringSync(json);
  }
  stderr.writeln('dart: $files files, $errors compile errors, '
      '${extractor.classes.length} classes, ${extractor.methods.length} methods, '
      '${extractor.calls.length} calls, ${extractor.apiCalls.length} api calls');
}

/// The Dart SDK to analyze against: \$ONELENS_DART_SDK, else the one behind `dart`
/// on PATH (Flutter's `bin/dart` wrapper keeps it in `bin/cache/dart-sdk`). A
/// compiled extractor has no SDK of its own, so it must find one.
String? dartSdk() {
  final env = Platform.environment['ONELENS_DART_SDK'];
  if (env != null && env.isNotEmpty) return env;
  for (final dir in (Platform.environment['PATH'] ?? '').split(':')) {
    final dart = File(p.join(dir, 'dart'));
    if (!dart.existsSync()) continue;
    final bin = p.dirname(dart.resolveSymbolicLinksSync());
    for (final sdk in [p.dirname(bin), p.join(bin, 'cache', 'dart-sdk')]) {
      if (File(p.join(sdk, 'version')).existsSync() && Directory(p.join(sdk, 'lib', 'core')).existsSync()) return sdk;
    }
  }
  return null;
}

class Extractor {
  Extractor(this.root);

  final String root;
  final classes = <Map<String, Object?>>[];
  final methods = <Map<String, Object?>>[];
  final fields = <Map<String, Object?>>[];
  final calls = <Map<String, Object?>>[];
  final inheritance = <Map<String, Object?>>[];
  final overrides = <Map<String, Object?>>[];
  final annotations = <Map<String, Object?>>[];
  final apiCalls = <Map<String, Object?>>[];
  final _seen = <String>{};

  Map<String, Object?> document(String name) => {
        'version': '1.0',
        'exportType': 'full',
        'project': {'name': name, 'basePath': root},
        'classes': classes,
        'methods': methods,
        'fields': fields,
        'callGraph': calls,
        'inheritance': inheritance,
        'methodOverrides': overrides,
        'annotations': annotations,
        'apiCalls': [
          for (final a in apiCalls) {...a, 'path': _fillConstants(a['path'] as String), 'parametric': _fillConstants(a['path'] as String).contains(r'${')},
        ],
        'adapters': ['dart-analyzer'],
      };

  late ResolvedUnitResult _unit;
  late String _rel;

  void unit(ResolvedUnitResult result) {
    _unit = result;
    _rel = p.relative(result.path, from: root);
    final library = result.libraryElement;
    _emitLibrary(library);
    result.unit.accept(_Walker(this));
  }

  // ---- names ---------------------------------------------------------------

  /// `package:acme/services/request_service.dart` -> `acme.services.request_service`,
  /// `dart:core` -> `dart.core`, a file outside `lib/` -> its path relative to the root.
  String libraryId(LibraryElement? library) {
    if (library == null) return '';
    final uri = library.uri;
    String path;
    switch (uri.scheme) {
      case 'package':
        path = uri.path;
      case 'dart':
        path = 'dart/${uri.path}';
      case 'file':
        path = p.relative(uri.toFilePath(), from: root);
      default:
        path = uri.toString();
    }
    if (path.endsWith('.dart')) path = path.substring(0, path.length - 5);
    return path.replaceAll(RegExp(r'[/\\]+'), '.');
  }

  String typeFqn(InstanceElement type) {
    final name = type.name ?? '<extension@${type.firstFragment.offset}>';
    return '${libraryId(type.library)}.$name';
  }

  /// Class (or, for top-level functions, the library) that owns [e].
  String ownerFqn(Element e) {
    final owner = e.enclosingElement;
    if (owner is InstanceElement) return typeFqn(owner);
    return libraryId(e.library);
  }

  String typeText(DartType? t) => t == null ? '' : t.getDisplayString();

  String executableFqn(ExecutableElement e) {
    final base = e.baseElement;
    final owner = ownerFqn(base);
    String member;
    if (base is ConstructorElement) {
      final cls = base.enclosingElement.name ?? '';
      final n = base.name;
      member = (n == null || n.isEmpty || n == 'new') ? cls : '$cls.$n';
    } else if (base is SetterElement) {
      member = '${base.name}=';
    } else {
      member = base.name ?? '';
    }
    final params = base.formalParameters.map((x) => typeText(x.type)).join(',');
    return '$owner#$member($params)';
  }

  int _line(int offset) => _unit.lineInfo.getLocation(offset).lineNumber;

  // ---- declarations --------------------------------------------------------

  final _libraries = <String>{};

  void _emitLibrary(LibraryElement library) {
    final id = libraryId(library);
    if (!_libraries.add(id)) return;
    // Top-level functions, getters and variables hang off one LIBRARY node per file.
    if (library.topLevelFunctions.isEmpty && library.topLevelVariables.isEmpty) return;
    classes.add({
      'fqn': id, 'name': p.basenameWithoutExtension(library.uri.path), 'kind': 'LIBRARY',
      'packageName': id, 'superClass': '', 'enclosingClass': '',
      'filePath': p.relative(library.firstFragment.source.fullName, from: root),
      'lineStart': 1, 'lineEnd': 0, 'source': 'TYPES',
    });
  }

  void type(AstNode node, InstanceElement? element, String kind) {
    if (element == null) return;
    final fqn = typeFqn(element);
    if (!_seen.add('C|$fqn')) return;
    String superClass = '';
    if (element is InterfaceElement) {
      final sup = element.supertype;
      if (sup != null && !sup.isDartCoreObject) superClass = typeFqn(sup.element);
      if (superClass.isNotEmpty) _inherit(fqn, superClass, 'EXTENDS');
      for (final i in element.interfaces) {
        _inherit(fqn, typeFqn(i.element), kind == 'INTERFACE' ? 'EXTENDS' : 'IMPLEMENTS');
      }
      // A mixin's members become the class's own members, like an interface it implements.
      for (final m in element.mixins) {
        _inherit(fqn, typeFqn(m.element), 'IMPLEMENTS');
      }
      if (element is MixinElement) {
        for (final c in element.superclassConstraints) {
          if (!c.isDartCoreObject) _inherit(fqn, typeFqn(c.element), 'IMPLEMENTS');
        }
      }
    }
    classes.add({
      'fqn': fqn, 'name': element.name ?? '', 'kind': kind,
      'packageName': libraryId(element.library), 'superClass': superClass,
      'enclosingClass': '',
      'filePath': _rel, 'lineStart': _line(node.offset), 'lineEnd': _line(node.end),
      'modifiers': [if (element.isPrivate) 'private' else 'public'],
      'javadoc': element.documentationComment ?? '',
      'annotations': _annotationRefs(element),
      'source': 'TYPES',
    });
    _annotate(element, fqn, 'CLASS');
  }

  void _inherit(String child, String parent, String relation) {
    if (_seen.add('I|$child|$parent|$relation')) {
      inheritance.add({'childFqn': child, 'parentFqn': parent, 'relationType': relation});
    }
  }

  String method(AstNode node, ExecutableElement? element, {FunctionBody? body}) {
    if (element == null) return '';
    final fqn = executableFqn(element);
    if (!_seen.add('M|$fqn')) return fqn;
    final isCtor = element is ConstructorElement;
    final mods = <String>[
      if (element.isPrivate) 'private' else 'public',
      if (element.isStatic) 'static',
      if (element.isAbstract) 'abstract',
      if (element.isExternal) 'external',
      if (body != null && body.isAsynchronous) 'async',
      if (body != null && body.isGenerator) 'generator',
      if (element is ConstructorElement && element.isFactory) 'factory',
      if (element is ConstructorElement && element.isConst) 'const',
      if (element is GetterElement) 'getter',
      if (element is SetterElement) 'setter',
    ];
    final src = _unit.content.substring(node.offset, node.end);
    methods.add({
      'fqn': fqn, 'name': isCtor ? (element.enclosingElement.name ?? '') : (element.name ?? ''),
      'classFqn': ownerFqn(element.baseElement),
      'returnType': isCtor ? '' : typeText(element.returnType),
      'parameters': [
        for (final x in element.formalParameters)
          {'name': x.name ?? '', 'type': typeText(x.type), 'annotations': []},
      ],
      'modifiers': mods, 'throwsTypes': [], 'annotations': _annotationRefs(element),
      'isConstructor': isCtor, 'filePath': _rel,
      'lineStart': _line(node.offset), 'lineEnd': _line(node.end),
      'body': src.length > 20000 ? src.substring(0, 20000) : src,
      'javadoc': element.documentationComment ?? '', 'source': 'TYPES',
    });
    _annotate(element, fqn, 'METHOD');
    _linkOverrides(element, fqn);
    return fqn;
  }

  void _linkOverrides(ExecutableElement element, String fqn) {
    if (element is ConstructorElement || element.isStatic) return;
    final owner = element.enclosingElement;
    final lookup = element.lookupName;
    if (owner is! InterfaceElement || lookup == null) return;
    final overridden = owner.getOverridden(Name.forLibrary(element.library, lookup)) ?? const [];
    for (final o in overridden) {
      final target = executableFqn(o);
      if (target != fqn && _seen.add('O|$fqn|$target')) {
        overrides.add({'methodFqn': fqn, 'overridesFqn': target});
      }
    }
  }

  /// Final/const String fields with a literal initializer, by field fqn. Paths
  /// often use `static final ASSET = "asset"`, which is not a compile-time
  /// constant, so the value is taken from the declaration.
  final _stringConstants = <String, String>{};

  String _fillConstants(String path) => path.replaceAllMapped(
        RegExp('\u0000([^\u0000]+)\u0000'),
        (m) => _stringConstants[m[1]] ?? r'${' + m[1]!.split('#').last + '}',
      );

  void field(AstNode node, VariableElement? element) {
    if (element == null) return;
    final owner = ownerFqn(element);
    final fqn = '$owner#${element.name}';
    if (node is VariableDeclaration && (element.isFinal || element.isConst) && node.initializer is SimpleStringLiteral) {
      _stringConstants[fqn] = (node.initializer as SimpleStringLiteral).value;
    }
    if (!_seen.add('F|$fqn')) return;
    fields.add({
      'fqn': fqn, 'name': element.name ?? '', 'classFqn': owner, 'type': typeText(element.type),
      'filePath': _rel, 'lineStart': _line(node.offset), 'source': 'TYPES',
      'modifiers': [
        if (element.isPrivate) 'private' else 'public',
        if (element.isStatic) 'static',
        if (element.isFinal) 'final',
        if (element.isConst) 'const',
      ],
    });
  }

  List<Map<String, String>> _annotationRefs(Element e) => [
        for (final a in e.metadata.annotations)
          if (_annotationType(a) case final t?) {'fqn': t, 'name': t.split('.').last},
      ];

  /// `@override` -> `dart.core.override`'s class is not useful; use the annotation's type:
  /// `@Deprecated('x')` and `@deprecated` both become `dart.core.Deprecated`.
  String? _annotationType(ElementAnnotation a) {
    final el = a.element;
    if (el is ConstructorElement) return typeFqn(el.enclosingElement);
    if (el is PropertyAccessorElement) {
      final t = el.returnType;
      if (t is InterfaceType) return typeFqn(t.element);
    }
    return null;
  }

  void _annotate(Element e, String target, String kind) {
    for (final a in e.metadata.annotations) {
      final t = _annotationType(a);
      if (t == null) continue;
      final source = a.toSource();
      final open = source.indexOf('(');
      final args = open < 0 ? '' : source.substring(open + 1, source.length - 1);
      annotations.add({
        'targetFqn': target, 'targetKind': kind, 'annotationFqn': t,
        'attributes': jsonEncode(args.isEmpty ? {} : {'value': args}),
        'attrValues': args.isEmpty ? {} : {'value': args},
      });
    }
  }

  // ---- calls ---------------------------------------------------------------

  void call(String caller, Element? target, int offset) {
    if (caller.isEmpty || target is! ExecutableElement) return;
    if (target is LocalFunctionElement) return;
    // Implicit getters/setters of fields are field access, not calls.
    if (target is PropertyAccessorElement && target.isOriginVariable) return;
    final callee = executableFqn(target);
    final line = _line(offset);
    if (caller.endsWith('#<init>()') && _seen.add('M|$caller')) {
      // Field and top-level variable initializers: one synthetic method per class/library.
      final owner = caller.substring(0, caller.length - '#<init>()'.length);
      methods.add({
        'fqn': caller, 'name': '<init>', 'classFqn': owner, 'returnType': '', 'parameters': [],
        'modifiers': ['static'], 'throwsTypes': [], 'annotations': [], 'isConstructor': false,
        'filePath': _rel, 'lineStart': line, 'lineEnd': line, 'body': '', 'javadoc': '',
        'source': 'TYPES',
      });
    }
    if (_seen.add('X|$caller|$callee|$line')) {
      calls.add({'callerFqn': caller, 'calleeFqn': callee, 'line': line});
    }
  }

  /// `client.get('/request/$id')`: an HTTP verb whose first argument binds a
  /// parameter named url/path/uri. One row per possible path (a ternary in the
  /// path yields both branches).
  void apiCall(String caller, MethodInvocation node) {
    final target = node.methodName.element;
    if (caller.isEmpty || target is! ExecutableElement) return;
    final verb = target.name?.toLowerCase();
    if (verb == null || !httpVerbs.contains(verb)) return;
    final args = node.argumentList.arguments;
    if (args.isEmpty || args.first is NamedArgument) return;
    final param = args.first.correspondingParameter;
    if (param == null || !urlParamNames.contains(param.name?.toLowerCase())) return;
    if (!param.type.isDartCoreString && param.type.getDisplayString() != 'Uri') return;
    for (final path in _pathVariants(args.first.argumentExpression).take(4)) {
      if (path.isEmpty) continue;
      apiCalls.add({
        'method': verb.toUpperCase(), 'path': path, 'parametric': path.contains(r'${'),
        'callerFqn': caller, 'filePath': _rel, 'line': _line(node.offset),
        'receiverType': ownerFqn(target.baseElement),
      });
    }
  }

  List<String> _pathVariants(Expression e) {
    if (e is SimpleStringLiteral) return [e.value];
    if (e is AdjacentStrings) return _concat(e.strings.map(_pathVariants).toList());
    if (e is StringInterpolation) {
      return _concat([
        for (final el in e.elements)
          if (el is InterpolationString) [el.value] else if (el is InterpolationExpression) _pathVariants(el.expression),
      ]);
    }
    if (e is ParenthesizedExpression) return _pathVariants(e.expression);
    if (e is ConditionalExpression) {
      return [..._pathVariants(e.thenExpression), ..._pathVariants(e.elseExpression)];
    }
    if (e is BinaryExpression && e.operator.lexeme == '+') {
      return _concat([_pathVariants(e.leftOperand), _pathVariants(e.rightOperand)]);
    }
    // A const String (e.g. `ApiPaths.requests`) contributes its value; anything else is a parameter.
    final ref = e is Identifier ? e.element : (e is PropertyAccess ? e.propertyName.element : null);
    final variable = ref is PropertyAccessorElement ? ref.variable : ref;
    if (variable is VariableElement && variable.isConst) {
      final v = variable.computeConstantValue()?.toStringValue();
      if (v != null) return [v];
    }
    if (variable is FieldElement || variable is TopLevelVariableElement) {
      final v = variable as VariableElement;
      if (v.isFinal || v.isConst) return ['\u0000${ownerFqn(v)}#${v.name}\u0000'];
    }
    return [r'${' + e.toSource() + '}'];
  }

  List<String> _concat(List<List<String>> parts) {
    var out = [''];
    for (final part in parts) {
      out = [for (final a in out) for (final b in part.isEmpty ? [''] : part) a + b];
      if (out.length > 8) out = out.sublist(0, 8);
    }
    return out;
  }
}

/// Walks one resolved unit: declarations open a scope, every resolved reference
/// inside a scope becomes a CALLS edge from that scope's method.
class _Walker extends RecursiveAstVisitor<void> {
  _Walker(this.x);

  final Extractor x;
  final _scope = <String>[];

  String get _caller => _scope.isEmpty ? '' : _scope.last;

  void _inside(String fqn, AstNode node) {
    _scope.add(fqn);
    node.visitChildren(this);
    _scope.removeLast();
  }

  @override
  void visitClassDeclaration(ClassDeclaration node) {
    final e = node.declaredFragment?.element;
    x.type(node, e, e == null ? 'CLASS' : (e.isAbstract || e.isInterface ? (e.isInterface ? 'INTERFACE' : 'ABSTRACT_CLASS') : 'CLASS'));
    _initializers(node, e);
  }

  @override
  void visitClassTypeAlias(ClassTypeAlias node) {
    final e = node.declaredFragment?.element;
    x.type(node, e, 'CLASS');
    super.visitClassTypeAlias(node);
  }

  @override
  void visitMixinDeclaration(MixinDeclaration node) {
    x.type(node, node.declaredFragment?.element, 'MIXIN');
    _initializers(node, node.declaredFragment?.element);
  }

  @override
  void visitEnumDeclaration(EnumDeclaration node) {
    x.type(node, node.declaredFragment?.element, 'ENUM');
    _initializers(node, node.declaredFragment?.element);
  }

  @override
  void visitExtensionDeclaration(ExtensionDeclaration node) {
    x.type(node, node.declaredFragment?.element, 'EXTENSION');
    _initializers(node, node.declaredFragment?.element);
  }

  @override
  void visitExtensionTypeDeclaration(ExtensionTypeDeclaration node) {
    x.type(node, node.declaredFragment?.element, 'EXTENSION_TYPE');
    _initializers(node, node.declaredFragment?.element);
  }

  /// Field initializers run as part of construction; attribute their calls to
  /// the class's static initializer so they are not lost.
  void _initializers(AstNode node, InstanceElement? owner) {
    if (owner == null) {
      node.visitChildren(this);
      return;
    }
    _inside('${x.typeFqn(owner)}#<init>()', node);
  }

  @override
  void visitMethodDeclaration(MethodDeclaration node) {
    final fqn = x.method(node, node.declaredFragment?.element, body: node.body);
    _inside(fqn, node);
  }

  @override
  void visitConstructorDeclaration(ConstructorDeclaration node) {
    final fqn = x.method(node, node.declaredFragment?.element, body: node.body);
    _inside(fqn, node);
  }

  @override
  void visitFunctionDeclaration(FunctionDeclaration node) {
    final e = node.declaredFragment?.element;
    // Local functions belong to the enclosing method.
    if (e is LocalFunctionElement) {
      super.visitFunctionDeclaration(node);
      return;
    }
    final fqn = x.method(node, e, body: node.functionExpression.body);
    _inside(fqn, node);
  }

  @override
  void visitFieldDeclaration(FieldDeclaration node) {
    for (final v in node.fields.variables) {
      x.field(v, v.declaredFragment?.element);
    }
    super.visitFieldDeclaration(node);
  }

  @override
  void visitTopLevelVariableDeclaration(TopLevelVariableDeclaration node) {
    for (final v in node.variables.variables) {
      x.field(v, v.declaredFragment?.element);
    }
    final lib = x.libraryId(node.declaredFragment?.element.library);
    _inside('$lib#<init>()', node);
  }

  @override
  void visitEnumConstantDeclaration(EnumConstantDeclaration node) {
    x.field(node, node.declaredFragment?.element);
    x.call(_caller, node.constructorElement, node.offset);
    super.visitEnumConstantDeclaration(node);
  }

  // ---- references ----------------------------------------------------------

  @override
  void visitSimpleIdentifier(SimpleIdentifier node) {
    // Declaration names resolve to themselves; skip them.
    if (!node.inDeclarationContext()) x.call(_caller, node.element, node.offset);
    super.visitSimpleIdentifier(node);
  }

  @override
  void visitMethodInvocation(MethodInvocation node) {
    x.apiCall(_caller, node);
    super.visitMethodInvocation(node);
  }

  @override
  void visitConstructorName(ConstructorName node) {
    x.call(_caller, node.element, node.offset);
    super.visitConstructorName(node);
  }

  @override
  void visitSuperConstructorInvocation(SuperConstructorInvocation node) {
    x.call(_caller, node.element, node.offset);
    super.visitSuperConstructorInvocation(node);
  }

  @override
  void visitRedirectingConstructorInvocation(RedirectingConstructorInvocation node) {
    x.call(_caller, node.element, node.offset);
    super.visitRedirectingConstructorInvocation(node);
  }

  @override
  void visitBinaryExpression(BinaryExpression node) {
    x.call(_caller, node.element, node.offset);
    super.visitBinaryExpression(node);
  }

  @override
  void visitIndexExpression(IndexExpression node) {
    x.call(_caller, node.element, node.offset);
    super.visitIndexExpression(node);
  }

  @override
  void visitPrefixExpression(PrefixExpression node) {
    x.call(_caller, node.element, node.offset);
    super.visitPrefixExpression(node);
  }

  @override
  void visitAssignmentExpression(AssignmentExpression node) {
    // `a.b = v` calls the setter `b=`; `a.b += v` also calls the getter `b`.
    x.call(_caller, node.writeElement, node.offset);
    x.call(_caller, node.readElement, node.offset);
    super.visitAssignmentExpression(node);
  }

  @override
  void visitPostfixExpression(PostfixExpression node) {
    x.call(_caller, node.writeElement, node.offset);
    x.call(_caller, node.readElement, node.offset);
    super.visitPostfixExpression(node);
  }

  @override
  void visitDotShorthandConstructorInvocation(DotShorthandConstructorInvocation node) {
    x.call(_caller, node.constructorName.element, node.offset);
    super.visitDotShorthandConstructorInvocation(node);
  }
}
