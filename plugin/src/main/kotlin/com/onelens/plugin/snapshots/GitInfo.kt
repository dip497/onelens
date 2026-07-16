package com.onelens.plugin.snapshots

import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import git4idea.branch.GitBranchUtil
import git4idea.repo.GitRepositoryManager

/**
 * Thin wrapper over `git4idea` exposing the three things the Snapshots UI needs:
 * current branch, HEAD commit sha, and the latest semver-ordered tag (for
 * pre-filling the Publish dialog).
 *
 * `GitRepositoryManager` is safe to call from EDT — it returns cached
 * repositories whose state is refreshed in the background. `getAllTags()`
 * shells to `git` and must be called from a background thread.
 */
object GitInfo {

    private val LOG = logger<GitInfo>()

    fun currentBranch(project: Project): String? =
        safe { repo(project)?.currentBranch?.name }

    fun headSha(project: Project): String? =
        safe { repo(project)?.currentRevision }

    // Latest tag sorted by semver (highest first). Shells to git — call from
    // a coroutine on Dispatchers.IO or a Task.Backgroundable.
    fun latestTag(project: Project): String? = safe {
        val r = repo(project) ?: return@safe null
        GitBranchUtil.getAllTags(project, r.root)
            .filter { it.isNotBlank() }
            .sortedWith(SEMVER_COMPARATOR.reversed())
            .firstOrNull()
    }

    // Wraps every Git4Idea call so a missing plugin (NoClassDefFoundError) or
    // runtime failure collapses to null instead of crashing the caller.
    private inline fun <T> safe(block: () -> T?): T? = try {
        block()
    } catch (e: Throwable) {
        LOG.info("git info unavailable: ${e.javaClass.simpleName}: ${e.message}")
        null
    }

    private fun repo(project: Project) =
        GitRepositoryManager.getInstance(project).repositories.firstOrNull()

    /**
     * Comparator for strings like `v1.2.3`, `1.2.3`, `v1.2.3-rc.1`. Non-semver
     * tags sort lexicographically after semver ones. No external dependency —
     * `git4idea` has no semver parser.
     */
    private val SEMVER_COMPARATOR: Comparator<String> = Comparator { a, b ->
        val pa = parseSemver(a)
        val pb = parseSemver(b)
        when {
            pa != null && pb != null -> compareSemver(pa, pb)
            pa != null -> -1
            pb != null -> 1
            else -> a.compareTo(b)
        }
    }

    private fun parseSemver(s: String): IntArray? {
        val body = s.removePrefix("v").substringBefore('-').substringBefore('+')
        val parts = body.split('.')
        if (parts.size !in 2..4) return null
        val nums = IntArray(parts.size)
        for ((i, p) in parts.withIndex()) {
            nums[i] = p.toIntOrNull() ?: return null
        }
        return nums
    }

    private fun compareSemver(a: IntArray, b: IntArray): Int {
        val n = maxOf(a.size, b.size)
        for (i in 0 until n) {
            val ai = a.getOrElse(i) { 0 }
            val bi = b.getOrElse(i) { 0 }
            if (ai != bi) return ai.compareTo(bi)
        }
        return 0
    }
}
