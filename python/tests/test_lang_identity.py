"""Language profiles + identity — Java behavior must stay byte-identical, and
structured fields / non-Java profiles must resolve correctly."""

from onelens.lang import identity, get_profile, all_entry_point_annotations, registered_langs


# ── Java equivalence: the new identity helpers vs the verbatim old parsing ─────

def _old_short_name(fqn):
    if "#" in fqn:
        return fqn.split("#")[1].split("(")[0]
    return fqn.split(".")[-1]

def _old_short_class(fqn):
    if "#" in fqn:
        fqn = fqn.split("#")[0]
    return fqn.split(".")[-1]

def _old_short_params(fqn):
    if "(" not in fqn:
        return ""
    params = fqn.split("(", 1)[1].rstrip(")")
    if not params:
        return "()"
    return "(" + ", ".join(p.split(".")[-1] for p in params.split(",")) + ")"


JAVA_FQNS = [
    "com.example.UserService#create(java.lang.String,int)",
    "com.example.UserService#create()",
    "com.example.Outer.Inner#doWork(java.util.List)",
    "com.example.UserService",
    "Plain",
]


def test_java_short_name_equivalence():
    for fqn in JAVA_FQNS:
        assert identity.simple_name(fqn) == _old_short_name(fqn), fqn

def test_java_short_class_equivalence():
    for fqn in JAVA_FQNS:
        assert identity.short_class(fqn) == _old_short_class(fqn), fqn

def test_java_short_params_equivalence():
    for fqn in JAVA_FQNS:
        assert identity.short_params(fqn) == _old_short_params(fqn), fqn


# ── Constructor detection ──────────────────────────────────────────────────────

def test_java_constructor_by_convention():
    assert identity.is_constructor("com.example.Foo#Foo()", lang="java") is True
    assert identity.is_constructor("com.example.Foo#bar()", lang="java") is False

def test_java_inner_class_constructor():
    # Outer$Inner constructor member name is "Inner" — must still detect.
    assert identity.is_constructor("com.example.Outer$Inner#Inner()", lang="java") is True
    assert identity.innermost_class("com.example.Outer$Inner#Inner()", lang="java") == "Inner"

def test_python_constructor_via_fixed_name():
    node = {"fqn": "app.svc:__init__", "simpleName": "__init__", "lang": "python"}
    assert identity.is_constructor(node) is True

def test_explicit_flag_overrides_syntax():
    assert identity.is_constructor({"isConstructor": True, "fqn": "x"}) is True
    assert identity.is_constructor(
        {"isConstructor": False, "fqn": "com.x.Foo#Foo()", "lang": "java"}
    ) is False


# ── Structured fields beat syntax (the new-extractor path) ─────────────────────

def test_structured_fields_override_syntax():
    n = {"fqn": "whatever::weird", "container": "my.Container",
         "simpleName": "doIt", "lang": "go"}
    assert identity.container_fqn(n) == "my.Container"
    assert identity.simple_name(n) == "doIt"


# ── Trivial members ────────────────────────────────────────────────────────────

def test_trivial_java_accessors():
    assert identity.is_trivial_member("getName", 1, "java") is True
    assert identity.is_trivial_member("getName", 5, "java") is False   # long body
    assert identity.is_trivial_member("toString", 10, "java") is True
    assert identity.is_trivial_member("compute", 1, "java") is False
    assert identity.is_trivial_member("get", 1, "java") is False       # no suffix

def test_trivial_python_dunders():
    assert identity.is_trivial_member("__str__", 1, "python") is True
    assert identity.is_trivial_member("getName", 1, "python") is False  # no getX convention


# ── Profiles / entry points ────────────────────────────────────────────────────

def test_entry_point_union_is_java_superset():
    ep = all_entry_point_annotations()
    for required in ["Scheduled", "PostConstruct", "EventListener", "KafkaListener"]:
        assert required in ep

def test_all_languages_registered():
    for lang in ["java", "kotlin", "python", "go", "csharp", "vue"]:
        assert lang in registered_langs()

def test_unknown_lang_falls_back_to_java():
    assert get_profile("rust").lang == "java"
    assert get_profile(None).lang == "java"
