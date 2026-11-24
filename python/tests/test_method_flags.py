"""Method flags derived at import: C# attributes and keywords map like Java annotations."""

from onelens.importer.graph_writer import _enrich_method


def test_java_deprecated_and_async_annotations():
    m = {"modifiers": ["public"], "annotations": [{"fqn": "java.lang.Deprecated"}, {"fqn": "org.springframework.scheduling.annotation.Async"}]}
    _enrich_method(m)
    assert m["isDeprecated"] and m["isAsync"]


def test_csharp_obsolete_attribute_is_deprecated():
    m = {"modifiers": ["public"], "annotations": [{"fqn": "System.ObsoleteAttribute"}]}
    _enrich_method(m)
    assert m["isDeprecated"]


def test_csharp_async_keyword_is_async():
    m = {"modifiers": ["public", "async"], "annotations": []}
    _enrich_method(m)
    assert m["isAsync"]


def test_plain_method_has_no_flags():
    m = {"modifiers": ["internal"], "annotations": []}
    _enrich_method(m)
    assert not m["isDeprecated"] and not m["isAsync"] and m["visibility"] == "package"
