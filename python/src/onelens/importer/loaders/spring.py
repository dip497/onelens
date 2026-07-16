"""SpringLoader — owns both the full and delta Spring import paths.

Extracted from loader.py (inline spring: node block ~174-203 + edge block ~441-468)
and delta_loader.py (_replace_spring) so the two paths cannot drift (the
wing-stamp drop that zeroed the Vue↔Spring HITS bridge prompted this extraction).
"""

import logging

from onelens.importer.loaders.base import SubdocLoader

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 500


def _chunks(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


class SpringLoader(SubdocLoader):
    json_key = "spring"

    def load_full(self, writer, progress, data: dict, wing: str) -> None:
        """Phase Spring — SpringBean/Endpoint/SpringAutoConfig nodes followed
        immediately by HANDLES/INJECTS/REGISTERED_AS edges.

        Both blocks are combined into one method so nodes exist before edges are
        wired. Call site is at the NODE-block location (~174) — after
        Class/Method/Field nodes, before Apps/Packages/JPA.
        """
        spring = data.get("spring")
        if not spring:
            return

        # --- NODES ---

        beans = []
        for b in spring.get("beans", []):
            b2 = dict(b, wing=wing)
            # Stringify activeProfiles so FalkorDB stores it as a scalar;
            # arrays are supported but inconsistent across client drivers.
            b2["activeProfiles"] = ",".join(b.get("activeProfiles") or [])
            b2["primary"] = bool(b.get("primary", False))
            b2["source"] = b.get("source") or "annotation"
            b2["factoryMethodFqn"] = b.get("factoryMethodFqn") or ""
            beans.append(b2)
        writer.batch_nodes(progress, "Spring Beans", beans, "SpringBean", "name", [
            "classFqn", "scope", "profile", "type", "wing",
            "primary", "source", "factoryMethodFqn", "activeProfiles",
        ])
        endpoints = spring.get("endpoints", [])
        for ep in endpoints:
            if "id" not in ep:
                ep["id"] = f"{ep.get('httpMethod', 'GET')}:{ep.get('path', '/')}"
            ep["wing"] = wing
        writer.batch_nodes(progress, "Endpoints", endpoints, "Endpoint", "id", [
            "path", "httpMethod", "controllerFqn", "handlerMethodFqn", "wing",
        ])

        autoconfigs = [dict(ac, wing=wing) for ac in spring.get("autoConfigs", [])]
        if autoconfigs:
            writer.batch_nodes(progress, "Auto-Configs", autoconfigs,
                               "SpringAutoConfig", "classFqn",
                               ["source", "sourceFile", "wing"])

        # --- EDGES ---

        handles = [{"src": ep["handlerMethodFqn"],
                    "dst": f"{ep.get('httpMethod', 'GET')}:{ep.get('path', '/')}"}
                   for ep in spring.get("endpoints", [])]
        writer.batch_edges(progress, "HANDLES", handles, "Method", "fqn", "Endpoint", "id")

        injects = [{"src": inj["targetClassFqn"], "dst": inj["injectedClassFqn"],
                    "field": inj.get("targetFieldOrParam", ""),
                    "type": inj.get("injectionType", ""),
                    "qualifier": inj.get("qualifier") or ""}
                   for inj in spring.get("injections", [])]
        writer.batch_edges_with_props(progress, "INJECTS", injects,
                                      "SpringBean", "classFqn", "SpringBean", "classFqn",
                                      ["field", "type", "qualifier"])

        # Class ↔ SpringBean bridge. We can't dual-label here — @Bean
        # factory methods produce beans without a 1:1 class identity (the
        # class is the bean's return type, not a registration marker on
        # itself). An explicit edge keeps the two concepts separate while
        # still letting `MATCH (c:Class {fqn:$x})-[:REGISTERED_AS]->(:SpringBean)`
        # answer "is this class exposed as a bean?" in one hop.
        reg_as = [{"src": b["classFqn"], "dst": b["name"]}
                  for b in spring.get("beans", [])
                  if b.get("classFqn") and b.get("name")]
        if reg_as:
            writer.batch_edges(progress, "REGISTERED_AS", reg_as,
                               "Class", "fqn", "SpringBean", "name")

    def apply_delta(self, writer, data: dict, wing: str) -> None:
        """Drop all SpringBean/Endpoint/AutoConfig/HANDLES/INJECTS/REGISTERED_AS,
        then re-insert with full-loader parity (props + wing + edges).

        Spring data is small (~2K beans on a 10K-class project) so a
        full replace is simpler and more correct than per-class diff —
        injections reference types on other classes, bean names can be
        renamed, and annotations can be added/removed without the
        annotated file showing up as "changed" if only a supertype
        changed.

        `wing` MUST match the full loader's stamp (loader.py:161-184): the
        Vue↔Spring HTTP bridge filters `Endpoint.wing IS NOT NULL`, so an
        unstamped Endpoint silently emits zero cross-stack HITS edges.
        """
        spring = data.get("spring")
        if not spring:
            return

        writer.db.execute("MATCH (b:SpringBean) DETACH DELETE b")
        # Endpoint is NO LONGER Spring-exclusive — the Next.js loader MERGEs Endpoint
        # nodes for its route handlers on the same `<METHOD>:<path>` PK. An unfiltered
        # global delete here wiped other wings' (and Next's) endpoints plus the HITS
        # bridge edges into them, from a single-wing delta. Scope it to this wing;
        # `_replace_nextjs` re-inserts this wing's Next endpoints afterwards.
        writer.db.execute(
            "MATCH (e:Endpoint) WHERE e.wing = $wing DETACH DELETE e", {"wing": wing}
        )
        writer.db.execute("MATCH (a:SpringAutoConfig) DETACH DELETE a")

        beans = spring.get("beans", []) or []
        bean_items = [{
            "name": b.get("name", ""), "classFqn": b.get("classFqn", ""),
            "type": b.get("type", ""), "scope": b.get("scope", ""),
            "profile": b.get("profile", ""), "wing": wing,
            "primary": bool(b.get("primary", False)),
            "source": b.get("source") or "annotation",
            "factoryMethodFqn": b.get("factoryMethodFqn") or "",
            "activeProfiles": ",".join(b.get("activeProfiles") or []),
        } for b in beans if b.get("name")]
        for batch in _chunks(bean_items, _CHUNK_SIZE):
            writer.db.execute("""
                UNWIND $batch AS item
                CREATE (b:SpringBean {name: item.name})
                SET b.classFqn = item.classFqn, b.type = item.type,
                    b.scope = item.scope, b.profile = item.profile,
                    b.wing = item.wing, b.primary = item.primary,
                    b.source = item.source,
                    b.factoryMethodFqn = item.factoryMethodFqn,
                    b.activeProfiles = item.activeProfiles
            """, {"batch": batch})

        # REGISTERED_AS (Class → SpringBean) — parity with loader.py:446-451.
        reg_as = [{"src": b["classFqn"], "dst": b["name"]}
                  for b in bean_items if b.get("classFqn") and b.get("name")]
        for batch in _chunks(reg_as, _CHUNK_SIZE):
            writer.db.execute("""
                UNWIND $batch AS edge
                MATCH (c:Class {fqn: edge.src}), (b:SpringBean {name: edge.dst})
                MERGE (c)-[:REGISTERED_AS]->(b)
            """, {"batch": batch})

        endpoints = spring.get("endpoints", []) or []
        ep_items = []
        handles = []
        for ep in endpoints:
            method = ep.get("httpMethod", "GET")
            path = ep.get("path", "/")
            ep_id = ep.get("id") or f"{method}:{path}"
            ep_items.append({
                "id": ep_id, "path": path, "httpMethod": method,
                "controllerFqn": ep.get("controllerFqn", ""),
                "handlerMethodFqn": ep.get("handlerMethodFqn", ""),
                "wing": wing,
            })
            if ep.get("handlerMethodFqn"):
                handles.append({"src": ep["handlerMethodFqn"], "dst": ep_id})

        for batch in _chunks(ep_items, _CHUNK_SIZE):
            writer.db.execute("""
                UNWIND $batch AS item
                CREATE (e:Endpoint {id: item.id})
                SET e.path = item.path, e.httpMethod = item.httpMethod,
                    e.controllerFqn = item.controllerFqn,
                    e.handlerMethodFqn = item.handlerMethodFqn,
                    e.wing = item.wing
            """, {"batch": batch})

        for batch in _chunks(handles, _CHUNK_SIZE):
            writer.db.execute("""
                UNWIND $batch AS edge
                MATCH (m:Method {fqn: edge.src}), (e:Endpoint {id: edge.dst})
                MERGE (m)-[:HANDLES]->(e)
            """, {"batch": batch})

        # SpringAutoConfig nodes — parity with loader.py:186-190.
        autoconfigs = [{
            "classFqn": ac.get("classFqn", ""), "source": ac.get("source", ""),
            "sourceFile": ac.get("sourceFile", ""), "wing": wing,
        } for ac in (spring.get("autoConfigs", []) or []) if ac.get("classFqn")]
        for batch in _chunks(autoconfigs, _CHUNK_SIZE):
            writer.db.execute("""
                UNWIND $batch AS item
                CREATE (a:SpringAutoConfig {classFqn: item.classFqn})
                SET a.source = item.source, a.sourceFile = item.sourceFile,
                    a.wing = item.wing
            """, {"batch": batch})

        # INJECTS edges live between SpringBean nodes keyed by classFqn.
        # DETACH DELETE above already dropped them; re-insert from the delta.
        # `qualifier` parity with loader.py:431-438.
        injections = spring.get("injections", []) or []
        inj_items = [{
            "src": inj.get("targetClassFqn", ""),
            "dst": inj.get("injectedClassFqn", ""),
            "field": inj.get("targetFieldOrParam", ""),
            "type": inj.get("injectionType", ""),
            "qualifier": inj.get("qualifier") or "",
        } for inj in injections if inj.get("targetClassFqn") and inj.get("injectedClassFqn")]
        for batch in _chunks(inj_items, _CHUNK_SIZE):
            writer.db.execute("""
                UNWIND $batch AS edge
                MATCH (a:SpringBean {classFqn: edge.src}),
                      (b:SpringBean {classFqn: edge.dst})
                MERGE (a)-[:INJECTS {field: edge.field, type: edge.type,
                                     qualifier: edge.qualifier}]->(b)
            """, {"batch": batch})

        logger.info(
            "Spring replaced: %d beans, %d endpoints, %d injections, %d autoconfigs (wing=%s)",
            len(bean_items), len(ep_items), len(inj_items), len(autoconfigs), wing,
        )
