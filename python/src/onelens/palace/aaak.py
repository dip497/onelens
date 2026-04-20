AAAK_SPEC = """AAAK is a compressed memory dialect. Palace stores verbatim Chroma drawers;
this spec is returned for agent compatibility. OneLens v1 does not compress
index layer — drawers remain readable Java/Kotlin/Vue source with canonical
metadata {wing, room, hall, fqn, type, importance, filed_at}.

FORMAT (reference, not enforced):
  ENTITIES: 3-letter uppercase codes.
  EMOTIONS: *markers* for emotional context.
  STRUCTURE: pipe-separated fields.
  DATES: ISO-8601. COUNTS: Nx. IMPORTANCE: * to ***** (1-5).
  HALLS: hall_code, hall_signature, hall_doc, hall_event, hall_fact.
  WINGS: source-scope slug (repo / project / agent:<name>).
  ROOMS: hyphenated slugs (Java package, ticket component, diary topic).

Read AAAK naturally — expand codes mentally, treat *markers* as emotional context.
"""
