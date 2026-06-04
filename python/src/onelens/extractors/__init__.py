"""
onelens.extractors — non-JVM language extractors that emit the normalized
OneLens JSON consumed by `GraphLoader`.

The IntelliJ plugin remains the extractor for JVM languages (Java/Kotlin) and,
per the IDE-plugin-centric decision, Go/Python/Vue will move into IntelliJ
Platform modules (GoLand/PyCharm/WebStorm). `vue_extractor` is a standalone,
dependency-free reference implementation: it proves the normalized contract and
the cross-stack data path end-to-end, and is fully unit-testable without an IDE.
"""
