package com.onelens.plugin.snapshots

// A snapshot already materialised under ~/.onelens/graphs/<graph>@<tag>/.
data class LocalSnapshot(
    val graph: String,
    val tag: String,
    val rdbPath: String,
    val rdbBytes: Long,
    val lastModified: Long,
) {
    // <graph>@<tag> — same string used by `onelens_status --graph …`.
    val graphName: String get() = "$graph@$tag"
}

// A published snapshot archive sitting at ~/.onelens/bundles/onelens-snapshot-<graph>-<tag>.tgz.
// Not yet extracted into graphs/. Install via `onelens_snapshots_pull --repo local`.
data class PublishedBundle(
    val graph: String,
    val tag: String,
    val tgzPath: String,
    val tgzBytes: Long,
    val lastModified: Long,
)
