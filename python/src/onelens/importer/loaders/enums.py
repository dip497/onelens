"""EnumLoader — owns both the full and delta enum-constant import paths.

Extracted from loader.py (inline dual-label block ~131-138 + HAS_ENUM_CONSTANT
edge block ~322-326) and delta_loader.py (inline re-creation block ~165-212)
so the two paths cannot drift (the dual-label split bug that prompted this
extraction).
"""

import logging

from onelens.importer.loaders.base import SubdocLoader

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 500


def _chunks(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


class EnumLoader(SubdocLoader):
    json_key = "enumConstants"

    def load_full(self, writer, progress, data: dict, wing: str) -> None:
        """Phase Enum — dual-label :Field:EnumConstant nodes followed
        immediately by HAS_ENUM_CONSTANT edges.

        Both blocks are combined into one method so nodes exist before edges
        are wired. Call site is at the NODE-block location (~131) — after
        Field nodes, before external stubs.
        """
        enum_constants = data.get("enumConstants", [])

        # Dual-label: an EnumConstant IS a Field. MemberCollector already
        # emits a Field with matching fqn for each enum constant; rather than
        # duplicating the node, tag the existing Field with :EnumConstant +
        # the enum-only props (args / argList).
        writer.batch_add_label(progress, "Enum Constants", enum_constants,
                               base_label="Field", base_pk="fqn", pk_field="fqn",
                               add_label="EnumConstant",
                               props=[
                                   "name", "ordinal", "enumFqn",
                                   "args", "argList", "argTypes",
                                   "filePath", "lineStart",
                               ])

        # HAS_ENUM_CONSTANT (Class → EnumConstant). Skipped when `enumConstants`
        # is empty (pre-1.1 exports / non-Java adapters).
        has_enum_const = [{"src": e["enumFqn"], "dst": e["fqn"]} for e in enum_constants]
        writer.batch_edges(progress, "HAS_ENUM_CONSTANT", has_enum_const,
                           "Class", "fqn", "EnumConstant", "fqn")

    def apply_delta(self, writer, data: dict, wing: str) -> None:
        """Strip + re-apply EnumConstant dual-labels and HAS_ENUM_CONSTANT edges.

        Strip the :EnumConstant label (not DETACH DELETE) from constants
        under upserted classes. Full import models an enum constant as a
        DUAL-LABEL on the Field node — one node carrying :Field:EnumConstant.
        DETACH-deleting by enumFqn here would destroy the shared Field node
        (and its HAS_FIELD edge) that the field upsert just re-created.
        REMOVE clears stale enum-ness while preserving the Field.
        """
        upserted = data.get("upserted", {})
        classes = upserted.get("classes", [])
        enum_consts = upserted.get("enumConstants", [])

        # Strip :EnumConstant label over upserted classes.
        upserted_class_fqn_list = [c["fqn"] for c in classes]
        for batch in _chunks(upserted_class_fqn_list, _CHUNK_SIZE):
            writer.db.execute(
                "UNWIND $batch AS fqn MATCH (e:EnumConstant {enumFqn: fqn}) "
                "REMOVE e:EnumConstant "
                "SET e.ordinal = null, e.enumFqn = null, e.args = null, "
                "    e.argList = null, e.argTypes = null",
                {"batch": batch}
            )

        # Dual-label on the existing Field node (created in the field upsert),
        # NOT a standalone :EnumConstant node — matches full import's single
        # :Field:EnumConstant node so `MATCH (:Field:EnumConstant)` and
        # HAS_FIELD→constant queries work identically on full and delta.
        for batch in _chunks(enum_consts, _CHUNK_SIZE):
            items = [{
                "fqn": e["fqn"], "name": e.get("name", ""),
                "ordinal": e.get("ordinal", 0), "enumFqn": e.get("enumFqn", ""),
                "args": e.get("args", "[]"),
                "argList": e.get("argList", []) or [],
                "argTypes": e.get("argTypes", []) or [],
                "filePath": e.get("filePath", ""),
                "lineStart": e.get("lineStart", 0),
            } for e in batch]
            writer.db.execute("""
                UNWIND $batch AS item
                MERGE (e:Field {fqn: item.fqn})
                SET e:EnumConstant,
                    e.name = item.name, e.ordinal = item.ordinal,
                    e.enumFqn = item.enumFqn, e.args = item.args,
                    e.argList = item.argList, e.argTypes = item.argTypes,
                    e.filePath = item.filePath, e.lineStart = item.lineStart
            """, {"batch": items})

        has_enum_const = [{"src": e.get("enumFqn", ""), "dst": e["fqn"]}
                          for e in enum_consts if e.get("enumFqn")]
        for batch in _chunks(has_enum_const, _CHUNK_SIZE):
            writer.db.execute("""
                UNWIND $batch AS edge
                MATCH (c:Class {fqn: edge.src}), (e:EnumConstant {fqn: edge.dst})
                MERGE (c)-[:HAS_ENUM_CONSTANT]->(e)
            """, {"batch": batch})
