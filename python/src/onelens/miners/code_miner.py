"""
code_miner.py — Transform OneLens JSON export into ChromaDB drawers.

Each method, class, and endpoint becomes a drawer with structural context
baked into the embedding text. This enables semantic search like
"find authentication logic" to match SecurityFilter#doFilter even if
"authentication" doesn't appear in the method name.

Performance (measured on RTX A2000 4GB, large Spring monorepo, 2026-04):
- ~30 drawers/sec end-to-end (embedding is the bottleneck)
- 49K drawers in ~22 minutes (74K methods → 37K after trivial filter,
  + 10K classes + 2K endpoints)
- Idempotent: re-run resumes via existing-ID check (no re-embedding)
"""

import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from onelens.context.config import OneLensContextConfig, HALL_CODE
from onelens.context.palace import get_collection

logger = logging.getLogger(__name__)

BATCH_SIZE = 500  # ChromaDB write batch (embedding is the bottleneck; batch stays small)

# Body/javadoc caps on the python side (second line of defense after plugin caps).
# Qwen3 max_seq=512 tokens ≈ 2000 chars; leave headroom for the metadata line.
MAX_BODY_CHARS = 2000
MAX_JAVADOC_CHARS = 500

# Trivial method patterns — skip these (no semantic value, ~45% of codebase)
_TRIVIAL_PREFIXES = ("get", "set", "is", "has", "can")
_TRIVIAL_NAMES = {"toString", "hashCode", "equals", "clone", "finalize"}


def _clean_javadoc(raw: str | None) -> str:
    """Strip /** */ and leading '*' from a Javadoc block. Returns empty if None."""
    if not raw:
        return ""
    text = raw.strip()
    if text.startswith("/**"):
        text = text[3:]
    if text.endswith("*/"):
        text = text[:-2]
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("*"):
            stripped = stripped[1:].strip()
        if stripped:
            lines.append(stripped)
    cleaned = " ".join(lines)
    return cleaned[:MAX_JAVADOC_CHARS]


def _is_trivial_method(method: dict) -> bool:
    """True if method is a getter/setter/toString/hashCode/equals.

    These add no semantic value to embeddings but make up ~45% of Java codebases.
    Skipping them halves indexing time without hurting search quality.
    """
    fqn = method.get("fqn", "")
    # Method name between '#' and '('
    name = fqn.split("#", 1)[1].split("(", 1)[0] if "#" in fqn else ""
    if not name:
        return False
    if name in _TRIVIAL_NAMES:
        return True
    # Small body heuristic: simple getters/setters are usually <= 3 lines
    body_size = method.get("lineEnd", 0) - method.get("lineStart", 0)
    if body_size <= 3:
        for prefix in _TRIVIAL_PREFIXES:
            if name.startswith(prefix) and len(name) > len(prefix) and name[len(prefix)].isupper():
                return True
    return False


class CodeMiner:
    """Mine OneLens JSON export into ChromaDB drawers with structural context."""

    def __init__(self, graph_name: str, config: OneLensContextConfig = None):
        self.graph_name = graph_name
        self.config = config or OneLensContextConfig()
        self.context_path = self.config.context_path(graph_name)
        self._collection = None

        # Pre-computed indexes (populated by _build_indexes)
        self._call_out = defaultdict(list)    # callerFqn -> [calleeFqn, ...]
        self._call_in = defaultdict(list)     # calleeFqn -> [callerFqn, ...]
        self._method_to_class = {}            # methodFqn -> classFqn
        self._class_methods = defaultdict(list)  # classFqn -> [methodFqn, ...]
        self._handler_to_endpoint = {}        # handlerFqn -> (httpMethod, path)
        self._endpoint_to_handler = {}        # "METHOD:path" -> handlerFqn
        self._method_annotations = defaultdict(list)  # fqn -> [annotationFqn, ...]
        self._class_annotations = defaultdict(list)
        self._injections = defaultdict(list)  # targetClassFqn -> [injectedClassFqn, ...]
        self._class_info = {}                 # classFqn -> dict

    def mine(self, export_path: Path) -> dict:
        """Mine the export JSON into ChromaDB. Returns stats dict."""
        t0 = time.time()

        print(f"Loading JSON ({export_path.name})...", flush=True)
        t1 = time.time()
        with open(export_path) as f:
            data = json.load(f)
        print(f"  JSON loaded in {time.time() - t1:.1f}s — "
              f"{len(data.get('methods', []))} methods, "
              f"{len(data.get('classes', []))} classes, "
              f"{len(data.get('callGraph', []))} call edges", flush=True)

        print("Building indexes...", flush=True)
        t2 = time.time()
        self._build_indexes(data)
        print(f"  Indexes built in {time.time() - t2:.1f}s", flush=True)

        print("Connecting to ChromaDB...", flush=True)
        self._collection = get_collection(self.context_path, create=True)

        from onelens.context.palace import get_max_batch_size, get_embedding_device
        max_bs = get_max_batch_size()
        device = get_embedding_device()
        self._actual_batch = min(BATCH_SIZE, max_bs)
        print(f"  ChromaDB ready. Embedding: {device}, max batch: {max_bs}, using: {self._actual_batch}", flush=True)

        stats = {"methods": 0, "classes": 0, "endpoints": 0}
        stats["methods"] = self._mine_methods(data)
        stats["classes"] = self._mine_classes(data)
        stats["endpoints"] = self._mine_endpoints(data)

        # Vue 3 — additive: only runs when the export carries a vue3 subdoc.
        # Drawers share the metadata schema with Java nodes (wing/room/hall/fqn/
        # type/importance/filed_at) so retrieval's wing+room filters work.
        if data.get("vue3"):
            stats["vue_components"] = self._mine_vue_components(data["vue3"])
            stats["vue_composables"] = self._mine_vue_composables(data["vue3"])
            stats["vue_stores"] = self._mine_vue_stores(data["vue3"])

        total_time = time.time() - t0
        total_drawers = sum(stats.values())
        print(f"\nDone! {total_drawers} drawers in {total_time:.1f}s "
              f"({total_drawers / max(total_time, 1):.0f} drawers/sec)", flush=True)

        return stats

    # ── Index building ────────────────────────────────────────────────────

    def _build_indexes(self, data: dict):
        """Pre-compute lookup structures for O(1) access during mining."""
        # Call graph
        for edge in data.get("callGraph", []):
            caller = edge["callerFqn"]
            callee = edge["calleeFqn"]
            self._call_out[caller].append(callee)
            self._call_in[callee].append(caller)

        # Method → class mapping
        for method in data.get("methods", []):
            fqn = method["fqn"]
            cls_fqn = method.get("classFqn", "")
            self._method_to_class[fqn] = cls_fqn
            self._class_methods[cls_fqn].append(fqn)

        # Endpoints
        spring = data.get("spring", {})
        for ep in spring.get("endpoints", []):
            handler = ep.get("handlerMethodFqn", "")
            http = ep.get("httpMethod", "")
            path = ep.get("path", "")
            if handler:
                self._handler_to_endpoint[handler] = (http, path)
                self._endpoint_to_handler[f"{http}:{path}"] = handler

        # Annotations (from top-level annotations list)
        for ann in data.get("annotations", []):
            target = ann.get("targetFqn", "")
            ann_fqn = ann.get("annotationFqn", "")
            kind = ann.get("targetKind", "")
            if kind == "METHOD":
                self._method_annotations[target].append(ann_fqn)
            elif kind == "CLASS":
                self._class_annotations[target].append(ann_fqn)

        # Spring injections
        for inj in spring.get("injections", []):
            target = inj.get("targetClassFqn", "")
            injected = inj.get("injectedClassFqn", "")
            if target and injected:
                self._injections[target].append(injected)

        # Class info
        for cls in data.get("classes", []):
            self._class_info[cls["fqn"]] = cls

    # ── Importance scoring ────────────────────────────────────────────────

    def _compute_importance(self, fqn: str, entity_type: str) -> float:
        """Score 0.0-1.0 based on fan-in, endpoint exposure, annotations."""
        score = 0.0

        if entity_type == "method":
            fan_in = len(self._call_in.get(fqn, []))
            score += min(fan_in / 20.0, 0.4)
            if fqn in self._handler_to_endpoint:
                score += 0.3
            anns = self._method_annotations.get(fqn, [])
            if any("Transactional" in a for a in anns):
                score += 0.15
            if any("Scheduled" in a for a in anns):
                score += 0.1
            if any("Async" in a for a in anns):
                score += 0.05

        elif entity_type == "class":
            methods = self._class_methods.get(fqn, [])
            total_fan_in = sum(len(self._call_in.get(m, [])) for m in methods)
            score += min(total_fan_in / 50.0, 0.4)
            score += min(len(methods) / 30.0, 0.2)
            injectors = len(self._injections.get(fqn, []))
            score += min(injectors / 10.0, 0.2)
            anns = self._class_annotations.get(fqn, [])
            if any("Service" in a or "Controller" in a or "Repository" in a for a in anns):
                score += 0.1

        elif entity_type == "endpoint":
            score += 0.5
            handler = self._endpoint_to_handler.get(fqn, "")
            if handler:
                fan_out = len(self._call_out.get(handler, []))
                score += min(fan_out / 15.0, 0.3)

        return round(min(score, 1.0), 3)

    # ── Document formatting ───────────────────────────────────────────────

    @staticmethod
    def _short_name(fqn: str) -> str:
        """Extract short class or method name from FQN."""
        if "#" in fqn:
            return fqn.split("#")[1].split("(")[0]
        return fqn.split(".")[-1]

    @staticmethod
    def _short_class(fqn: str) -> str:
        """Extract short class name from FQN."""
        if "#" in fqn:
            fqn = fqn.split("#")[0]
        return fqn.split(".")[-1]

    @staticmethod
    def _short_params(fqn: str) -> str:
        """Extract shortened parameter list from method FQN."""
        if "(" not in fqn:
            return ""
        params = fqn.split("(", 1)[1].rstrip(")")
        if not params:
            return "()"
        short = ", ".join(p.split(".")[-1] for p in params.split(","))
        return f"({short})"

    def _format_method_document(self, method: dict) -> str:
        """Build embedding text for a method drawer.

        Layout (when body/javadoc available):
            ClassName#name(params) | @Anns | calls: X,Y | calledBy: Z | endpoint: GET /foo
            ---
            <stripped javadoc>
            ---
            <method body>

        The metadata line keeps graph-derived context (calls/callers/endpoint)
        that doesn't appear in the body. The body gives Qwen3 actual logic to
        match against — the main +15-20% quality lever vs signature-only docs.
        """
        fqn = method["fqn"]
        class_name = self._short_class(fqn)
        method_name = self._short_name(fqn)
        params = self._short_params(fqn)

        # Annotations
        anns = self._method_annotations.get(fqn, [])
        ann_str = " ".join(f"@{a.split('.')[-1]}" for a in anns[:5])

        # Callees (what this method calls)
        callees = self._call_out.get(fqn, [])
        callee_names = sorted(set(
            f"{self._short_class(c)}.{self._short_name(c)}"
            for c in callees[:10]
        ))

        # Callers (who calls this method)
        callers = self._call_in.get(fqn, [])
        caller_names = sorted(set(
            f"{self._short_class(c)}.{self._short_name(c)}"
            for c in callers[:8]
        ))

        # Endpoint
        endpoint = self._handler_to_endpoint.get(fqn)

        parts = [f"{class_name}#{method_name}{params}"]
        if ann_str:
            parts.append(f"| {ann_str}")
        if callee_names:
            parts.append(f"| calls: {', '.join(callee_names[:8])}")
        if caller_names:
            parts.append(f"| calledBy: {', '.join(caller_names[:5])}")
        if endpoint:
            parts.append(f"| endpoint: {endpoint[0]} {endpoint[1]}")

        header = " ".join(parts)

        javadoc = _clean_javadoc(method.get("javadoc"))
        body = method.get("body")
        if body:
            body = body[:MAX_BODY_CHARS]

        sections = [header]
        if javadoc:
            sections.append(javadoc)
        if body:
            sections.append(body)
        return "\n---\n".join(sections)

    def _format_class_document(self, cls: dict) -> str:
        """Build embedding text for a class drawer."""
        fqn = cls["fqn"]
        name = cls["name"]
        kind = cls.get("kind", "CLASS")

        anns = self._class_annotations.get(fqn, [])
        ann_str = " ".join(f"@{a.split('.')[-1]}" for a in anns[:5])

        method_count = len(self._class_methods.get(fqn, []))
        super_class = cls.get("superClass")
        interfaces = cls.get("interfaces", [])
        injected = self._injections.get(fqn, [])

        parts = [name]
        if kind != "CLASS":
            parts.append(f"({kind.lower()})")
        if ann_str:
            parts.append(f"| {ann_str}")
        parts.append(f"| {method_count} methods")
        if super_class:
            parts.append(f"| extends {super_class.split('.')[-1]}")
        if interfaces:
            iface_names = [i.split(".")[-1] for i in interfaces[:5]]
            parts.append(f"| implements {', '.join(iface_names)}")
        if injected:
            inj_names = sorted(set(i.split(".")[-1] for i in injected[:8]))
            parts.append(f"| injected: {', '.join(inj_names)}")

        return " ".join(parts)

    def _format_endpoint_document(self, endpoint: dict) -> str:
        """Build embedding text for an endpoint drawer."""
        http = endpoint.get("httpMethod", "")
        path = endpoint.get("path", "")
        handler_fqn = endpoint.get("handlerMethodFqn", "")

        handler_short = ""
        if handler_fqn:
            handler_short = f"{self._short_class(handler_fqn)}#{self._short_name(handler_fqn)}"

        # What the handler calls
        callees = self._call_out.get(handler_fqn, [])
        callee_names = sorted(set(
            f"{self._short_class(c)}.{self._short_name(c)}"
            for c in callees[:8]
        ))

        parts = [f"{http} {path}"]
        if handler_short:
            parts.append(f"| {handler_short}")
        if callee_names:
            parts.append(f"| calls: {', '.join(callee_names[:8])}")

        return " ".join(parts)

    # ── External-embedder flow (used by TEI / vLLM / Arctic paths) ───────
    # These emit {id, document, metadata} tuples WITHOUT calling the
    # embedder. The caller (e.g. modal_index_tei.py) batches docs to a
    # remote inference server, then upserts to ChromaDB with pre-computed
    # embeddings. Skips the trivial-method/resume-ID filters that the
    # in-process mine() uses — those are the caller's responsibility.

    def iter_drawers(self, data: dict, skip_existing: set = None):
        """Yield {id, document, metadata} dicts for every drawer in `data`.

        Uses the same filters as mine() — trivial method skip, constructor
        skip, empty-filePath skip — but never touches ChromaDB or torch.
        If `skip_existing` is passed, drawers with IDs in that set are
        skipped (mirrors the resume-on-crash behavior of mine()).
        """
        skip = skip_existing or set()
        self._build_indexes(data)

        # Methods
        for m in data.get("methods", []):
            if not m.get("filePath") or m.get("isConstructor"):
                continue
            if _is_trivial_method(m):
                continue
            fqn = m["fqn"]
            drawer_id = f"method:{fqn}"
            if drawer_id in skip:
                continue
            cls_fqn = m.get("classFqn", "")
            pkg = cls_fqn.rsplit(".", 1)[0] if "." in cls_fqn else ""
            yield {
                "id": drawer_id,
                "document": self._format_method_document(m),
                "metadata": {
                    "wing": self.graph_name,
                    "room": pkg,
                    "hall": HALL_CODE,
                    "fqn": fqn,
                    "type": "method",
                    "importance": self._compute_importance(fqn, "method"),
                    "filed_at": datetime.now().isoformat(),
                },
            }

        # Classes
        for cls in data.get("classes", []):
            if not cls.get("filePath"):
                continue
            fqn = cls["fqn"]
            drawer_id = f"class:{fqn}"
            if drawer_id in skip:
                continue
            yield {
                "id": drawer_id,
                "document": self._format_class_document(cls),
                "metadata": {
                    "wing": self.graph_name,
                    "room": cls.get("packageName", ""),
                    "hall": HALL_CODE,
                    "fqn": fqn,
                    "type": "class",
                    "importance": self._compute_importance(fqn, "class"),
                    "filed_at": datetime.now().isoformat(),
                },
            }

        # Endpoints
        for ep in data.get("spring", {}).get("endpoints", []):
            http = ep.get("httpMethod", "")
            path = ep.get("path", "")
            handler = ep.get("handlerMethodFqn", "")
            drawer_id = f"endpoint:{http}:{path}:{handler}" if handler else f"endpoint:{http}:{path}"
            if drawer_id in skip:
                continue
            controller = ep.get("controllerFqn", "")
            pkg = controller.rsplit(".", 1)[0] if "." in controller else ""
            ep_fqn = f"{http}:{path}"
            yield {
                "id": drawer_id,
                "document": self._format_endpoint_document(ep),
                "metadata": {
                    "wing": self.graph_name,
                    "room": pkg,
                    "hall": HALL_CODE,
                    "fqn": ep_fqn,
                    "type": "endpoint",
                    "importance": self._compute_importance(ep_fqn, "endpoint"),
                    "filed_at": datetime.now().isoformat(),
                },
            }

    # ── Mining (batch upsert) ─────────────────────────────────────────────

    def _flush_batch(self, documents, ids, metadatas):
        """Upsert a batch to ChromaDB."""
        if not documents:
            return
        self._collection.upsert(documents=documents, ids=ids, metadatas=metadatas)

    def _get_existing_ids(self, prefix: str) -> set:
        """Return set of IDs already in ChromaDB with the given prefix.

        Used to resume a crashed import without re-embedding everything.
        """
        try:
            result = self._collection.get(include=[])  # IDs only
            all_ids = result.get("ids", [])
            return {i for i in all_ids if i.startswith(prefix)}
        except Exception:
            return set()

    # ── Delta support ────────────────────────────────────────────────────────

    def _ensure_collection(self):
        """Lazy-initialize ChromaDB collection for delta operations.

        The full `mine()` path opens the collection inside `_build_indexes`;
        delta helpers skip that, so they open it on first use here.
        """
        if self._collection is None:
            self._collection = get_collection(self.context_path, create=True)

    def delete_by_ids(self, ids: list[str]) -> int:
        """Delete drawers from ChromaDB by explicit ID list.

        Used by delta sync when source files / classes / methods are removed.
        IDs use the same format as `mine`: `method:<fqn>`, `class:<fqn>`,
        `endpoint:<id>`. Missing IDs are silently ignored by ChromaDB.
        Returns count of IDs requested (actual deletions are best-effort).
        """
        if not ids:
            return 0
        self._ensure_collection()
        try:
            self._collection.delete(ids=ids)
            return len(ids)
        except Exception as e:
            logger.warning("ChromaDB delete_by_ids failed: %s", e)
            return 0

    def delete_methods_of_classes(self, class_fqns: list[str]) -> int:
        """Cascade-delete every method drawer whose owning class is in the list.

        We rely on the ID prefix — every method drawer is keyed as
        `method:<classFqn>#<signature>`, so listing all IDs in the
        collection and filtering by `id.startswith("method:<classFqn>#")`
        finds exactly the drawers whose owning class was deleted. No
        metadata dependency, works on drawers from any historical schema.

        Returns the number of drawers actually deleted.
        """
        if not class_fqns:
            return 0
        self._ensure_collection()
        try:
            # One full scan of the collection IDs (cheap — IDs are short).
            result = self._collection.get(include=[])
            all_ids: list[str] = result.get("ids", []) or []
            prefixes = tuple(f"method:{fqn}#" for fqn in class_fqns)
            to_delete = [i for i in all_ids if i.startswith(prefixes)]
            if not to_delete:
                return 0
            # Chroma accepts batched ID lists; keep under ~1000 per call.
            BATCH = 500
            for i in range(0, len(to_delete), BATCH):
                self._collection.delete(ids=to_delete[i : i + BATCH])
            return len(to_delete)
        except Exception as e:
            logger.warning("ChromaDB cascade method delete failed: %s", e)
            return 0

    def mine_upserts(self, delta_data: dict) -> dict:
        """Re-embed just the methods / classes listed in a delta payload.

        Accepts a subset of the export JSON shape: {classes, methods, callGraph}.
        Builds local indexes from the delta alone (call_in/out is partial but
        sufficient for correct embedding text) and upserts each drawer with
        its canonical ID so prior versions are replaced in place.

        Skipped for external methods (no filePath) and constructors, matching
        the policy in `_mine_methods`.
        """
        self._ensure_collection()

        methods = [
            m for m in delta_data.get("methods", [])
            if m.get("filePath") and not m.get("isConstructor")
        ]
        methods = [m for m in methods if not _is_trivial_method(m)]
        classes = [c for c in delta_data.get("classes", []) if c.get("filePath")]

        # Partial index build — just enough for call_out / call_in so the
        # formatter's "calls: X, Y / calledBy: W, Z" context renders.
        call_out = defaultdict(list)
        call_in = defaultdict(list)
        for call in delta_data.get("callGraph", []):
            src = call.get("callerFqn")
            dst = call.get("calleeFqn")
            if src and dst:
                call_out[src].append(dst)
                call_in[dst].append(src)

        # Swap the miner's indexes for this operation. Restore after so
        # concurrent full mines aren't corrupted (though we don't currently
        # run them concurrently).
        prev_out, prev_in = self._call_out, self._call_in
        self._call_out, self._call_in = call_out, call_in

        try:
            m_count = 0
            c_count = 0
            batch_size = 64
            docs: list[str] = []
            ids: list[str] = []
            metas: list[dict] = []

            def flush():
                nonlocal docs, ids, metas
                if docs:
                    self._collection.upsert(documents=docs, ids=ids, metadatas=metas)
                    docs, ids, metas = [], [], []

            for m in methods:
                fqn = m.get("fqn")
                if not fqn:
                    continue
                docs.append(self._format_method_document(m))
                ids.append(f"method:{fqn}")
                metas.append(self._method_metadata(m))
                m_count += 1
                if len(docs) >= batch_size:
                    flush()
            flush()

            for c in classes:
                fqn = c.get("fqn")
                if not fqn:
                    continue
                docs.append(self._format_class_document(c))
                ids.append(f"class:{fqn}")
                metas.append(self._class_metadata(c))
                c_count += 1
                if len(docs) >= batch_size:
                    flush()
            flush()

            return {"methods_upserted": m_count, "classes_upserted": c_count}
        finally:
            self._call_out, self._call_in = prev_out, prev_in

    def _method_metadata(self, m: dict) -> dict:
        """Canonical drawer metadata for a method, matching `_mine_methods`
        (code_miner.py:677-685) exactly so semantic search filters that use
        `wing = graph_name` still hit drawers written via delta upsert.
        Adding new keys would be fine; dropping any breaks wing-scoped search.
        """
        fqn = m.get("fqn", "")
        cls_fqn = m.get("classFqn", "")
        pkg = cls_fqn.rsplit(".", 1)[0] if "." in cls_fqn else ""
        return {
            "wing": self.graph_name,
            "room": pkg,
            "hall": HALL_CODE,
            "fqn": fqn,
            "type": "method",
            "importance": self._compute_importance(fqn, "method"),
            "filed_at": datetime.now().isoformat(),
        }

    def _class_metadata(self, c: dict) -> dict:
        """Canonical drawer metadata for a class, matching `_mine_classes`
        (code_miner.py:718-733). See `_method_metadata` for the rationale.
        """
        fqn = c.get("fqn", "")
        return {
            "wing": self.graph_name,
            "room": c.get("packageName", ""),
            "hall": HALL_CODE,
            "fqn": fqn,
            "type": "class",
            "importance": self._compute_importance(fqn, "class"),
            "filed_at": datetime.now().isoformat(),
        }

    def _mine_methods(self, data: dict) -> int:
        """Mine all project methods into ChromaDB. Returns count."""
        all_methods = [
            m for m in data.get("methods", [])
            if m.get("filePath") and not m.get("isConstructor")
        ]
        methods = [m for m in all_methods if not _is_trivial_method(m)]
        skipped_trivial = len(all_methods) - len(methods)

        # Skip methods already embedded (resume after crash/OOM)
        existing = self._get_existing_ids("method:")
        if existing:
            methods = [m for m in methods if f"method:{m['fqn']}" not in existing]

        batch_size = getattr(self, "_actual_batch", BATCH_SIZE)
        print(
            f"Mining {len(methods)} methods "
            f"(skipped {skipped_trivial} trivial, {len(existing)} already indexed, "
            f"batch={batch_size})...",
            flush=True,
        )

        documents, ids, metadatas = [], [], []
        done = 0
        t_start = time.time()

        for method in methods:
            fqn = method["fqn"]
            doc = self._format_method_document(method)
            cls_fqn = method.get("classFqn", "")
            pkg = cls_fqn.rsplit(".", 1)[0] if "." in cls_fqn else ""

            documents.append(doc)
            ids.append(f"method:{fqn}")
            metadatas.append({
                "wing": self.graph_name,
                "room": pkg,
                "hall": HALL_CODE,
                "fqn": fqn,
                "type": "method",
                "importance": self._compute_importance(fqn, "method"),
                "filed_at": datetime.now().isoformat(),
            })

            if len(documents) >= batch_size:
                t_batch = time.time()
                self._flush_batch(documents, ids, metadatas)
                done += len(documents)
                elapsed = time.time() - t_start
                batch_time = time.time() - t_batch
                rate = done / max(elapsed, 0.1)
                print(f"  methods: {done}/{len(methods)} ({rate:.0f}/s, batch={batch_time:.1f}s)", flush=True)
                documents, ids, metadatas = [], [], []

        if documents:
            self._flush_batch(documents, ids, metadatas)
            done += len(documents)

        elapsed = time.time() - t_start
        print(f"  Methods done: {done} in {elapsed:.1f}s ({done / max(elapsed, 0.1):.0f}/s)", flush=True)
        return done

    def _mine_classes(self, data: dict) -> int:
        """Mine all project classes into ChromaDB. Returns count."""
        classes = [c for c in data.get("classes", []) if c.get("filePath")]
        existing = self._get_existing_ids("class:")
        if existing:
            classes = [c for c in classes if f"class:{c['fqn']}" not in existing]
        batch_size = getattr(self, "_actual_batch", BATCH_SIZE)
        print(f"Mining {len(classes)} classes ({len(existing)} already indexed)...", flush=True)

        documents, ids, metadatas = [], [], []
        done = 0
        t_start = time.time()

        for cls in classes:
            fqn = cls["fqn"]
            doc = self._format_class_document(cls)
            pkg = cls.get("packageName", "")

            documents.append(doc)
            ids.append(f"class:{fqn}")
            metadatas.append({
                "wing": self.graph_name,
                "room": pkg,
                "hall": HALL_CODE,
                "fqn": fqn,
                "type": "class",
                "importance": self._compute_importance(fqn, "class"),
                "filed_at": datetime.now().isoformat(),
            })

            if len(documents) >= batch_size:
                t_batch = time.time()
                self._flush_batch(documents, ids, metadatas)
                done += len(documents)
                elapsed = time.time() - t_start
                batch_time = time.time() - t_batch
                print(f"  classes: {done}/{len(classes)} (batch={batch_time:.1f}s)", flush=True)
                documents, ids, metadatas = [], [], []

        if documents:
            self._flush_batch(documents, ids, metadatas)
            done += len(documents)

        elapsed = time.time() - t_start
        print(f"  Classes done: {done} in {elapsed:.1f}s", flush=True)
        return done

    def _mine_endpoints(self, data: dict) -> int:
        """Mine all REST endpoints into ChromaDB. Returns count."""
        all_endpoints = data.get("spring", {}).get("endpoints", [])
        existing = self._get_existing_ids("endpoint:")

        def _ep_id(ep):
            http = ep.get("httpMethod", "")
            path = ep.get("path", "")
            handler = ep.get("handlerMethodFqn", "")
            return f"endpoint:{http}:{path}:{handler}" if handler else f"endpoint:{http}:{path}"

        endpoints = [ep for ep in all_endpoints if _ep_id(ep) not in existing]
        batch_size = getattr(self, "_actual_batch", BATCH_SIZE)
        print(
            f"Mining {len(endpoints)} endpoints "
            f"({len(existing)} already indexed)...",
            flush=True,
        )

        documents, ids, metadatas = [], [], []
        done = 0
        t_start = time.time()

        for ep in endpoints:
            http = ep.get("httpMethod", "")
            path = ep.get("path", "")
            ep_id = f"{http}:{path}"
            doc = self._format_endpoint_document(ep)

            handler = ep.get("handlerMethodFqn", "")
            controller = ep.get("controllerFqn", "")
            pkg = controller.rsplit(".", 1)[0] if "." in controller else ""

            # Use handler FQN in ID to avoid duplicates (same path, different controllers)
            unique_id = f"endpoint:{ep_id}:{handler}" if handler else f"endpoint:{ep_id}"
            documents.append(doc)
            ids.append(unique_id)
            metadatas.append({
                "wing": self.graph_name,
                "room": pkg,
                "hall": HALL_CODE,
                "fqn": ep_id,
                "type": "endpoint",
                "importance": self._compute_importance(ep_id, "endpoint"),
                "filed_at": datetime.now().isoformat(),
            })

            if len(documents) >= batch_size:
                self._flush_batch(documents, ids, metadatas)
                done += len(documents)
                documents, ids, metadatas = [], [], []

        if documents:
            self._flush_batch(documents, ids, metadatas)
            done += len(documents)

        elapsed = time.time() - t_start
        print(f"  Endpoints done: {done} in {elapsed:.1f}s", flush=True)
        return done

    # ── Vue 3 ─────────────────────────────────────────────────────────────
    #
    # Separate mining pass for Vue nodes. Kept small on purpose — just enough
    # to let semantic retrieval find components/stores/composables by intent.
    # The Kotlin side already truncated `body` fields to 2000 chars.

    def _vue_room(self, file_path: str) -> str:
        """Relative directory path used as the drawer's `room` metadata key."""
        if not file_path:
            return ""
        norm = file_path.replace("\\", "/")
        idx = norm.rfind("/")
        return norm[:idx] if idx > 0 else ""

    def _mine_vue_components(self, vue3: dict) -> int:
        components = [c for c in vue3.get("components", []) if c.get("filePath")]
        existing = self._get_existing_ids("component:")
        components = [c for c in components if f"component:{c['filePath']}" not in existing]
        batch_size = getattr(self, "_actual_batch", BATCH_SIZE)
        print(f"Mining {len(components)} Vue components ({len(existing)} already indexed)...", flush=True)

        documents, ids, metadatas = [], [], []
        done = 0
        t_start = time.time()
        for comp in components:
            fp = comp["filePath"]
            name = comp.get("name", "")
            body = (comp.get("body") or "").strip()
            doc = f"// Component: {name}\n// File: {fp}\n{body}" if body else f"// Component: {name}\n// File: {fp}"
            drawer_id = f"component:{fp}"
            documents.append(doc)
            ids.append(drawer_id)
            metadatas.append({
                "wing": self.graph_name,
                "room": self._vue_room(fp),
                "hall": HALL_CODE,
                "fqn": drawer_id,
                "type": "component",
                "importance": 0.0,
                "filed_at": datetime.now().isoformat(),
            })
            if len(documents) >= batch_size:
                self._flush_batch(documents, ids, metadatas)
                done += len(documents)
                documents, ids, metadatas = [], [], []
        if documents:
            self._flush_batch(documents, ids, metadatas)
            done += len(documents)

        elapsed = time.time() - t_start
        print(f"  Components done: {done} in {elapsed:.1f}s", flush=True)
        return done

    def _mine_vue_composables(self, vue3: dict) -> int:
        items = [c for c in vue3.get("composables", []) if c.get("fqn")]
        existing = self._get_existing_ids("composable:")
        items = [c for c in items if f"composable:{c['fqn']}" not in existing]
        batch_size = getattr(self, "_actual_batch", BATCH_SIZE)
        print(f"Mining {len(items)} Vue composables ({len(existing)} already indexed)...", flush=True)

        documents, ids, metadatas = [], [], []
        done = 0
        t_start = time.time()
        for comp in items:
            fqn = comp["fqn"]
            name = comp.get("name", "")
            fp = comp.get("filePath", "")
            body = (comp.get("body") or "").strip()
            doc = f"// Composable: {name}\n// File: {fp}\n{body}" if body else f"// Composable: {name}\n// File: {fp}"
            drawer_id = f"composable:{fqn}"
            documents.append(doc)
            ids.append(drawer_id)
            metadatas.append({
                "wing": self.graph_name,
                "room": self._vue_room(fp),
                "hall": HALL_CODE,
                "fqn": drawer_id,
                "type": "composable",
                "importance": 0.0,
                "filed_at": datetime.now().isoformat(),
            })
            if len(documents) >= batch_size:
                self._flush_batch(documents, ids, metadatas)
                done += len(documents)
                documents, ids, metadatas = [], [], []
        if documents:
            self._flush_batch(documents, ids, metadatas)
            done += len(documents)

        elapsed = time.time() - t_start
        print(f"  Composables done: {done} in {elapsed:.1f}s", flush=True)
        return done

    def _mine_vue_stores(self, vue3: dict) -> int:
        stores = [s for s in vue3.get("stores", []) if s.get("id")]
        existing = self._get_existing_ids("store:")
        stores = [s for s in stores if f"store:{s['id']}" not in existing]
        batch_size = getattr(self, "_actual_batch", BATCH_SIZE)
        print(f"Mining {len(stores)} Vue stores ({len(existing)} already indexed)...", flush=True)

        documents, ids, metadatas = [], [], []
        done = 0
        t_start = time.time()
        for store in stores:
            sid = store["id"]
            name = store.get("name", "")
            fp = store.get("filePath", "")
            body = (store.get("body") or "").strip()
            doc = f"// Store: {sid} (export {name})\n// File: {fp}\n{body}" if body else f"// Store: {sid} (export {name})\n// File: {fp}"
            drawer_id = f"store:{sid}"
            documents.append(doc)
            ids.append(drawer_id)
            metadatas.append({
                "wing": self.graph_name,
                "room": self._vue_room(fp),
                "hall": HALL_CODE,
                "fqn": drawer_id,
                "type": "store",
                "importance": 0.0,
                "filed_at": datetime.now().isoformat(),
            })
            if len(documents) >= batch_size:
                self._flush_batch(documents, ids, metadatas)
                done += len(documents)
                documents, ids, metadatas = [], [], []
        if documents:
            self._flush_batch(documents, ids, metadatas)
            done += len(documents)

        elapsed = time.time() - t_start
        print(f"  Stores done: {done} in {elapsed:.1f}s", flush=True)
        return done
