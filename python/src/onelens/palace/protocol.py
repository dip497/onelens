PROTOCOL = """IMPORTANT — OneLens Palace Protocol:
1. ON WAKE-UP: call palace_status to load wings, rooms, halls, taxonomy, protocol.
2. BEFORE RESPONDING about any code symbol, ticket, incident, or fact:
     - structural  → palace_kg_query (include_structural=True) or existing impact/trace
     - textual     → palace_search
   Never guess. Verify.
3. IF UNSURE (FQN, owner, current status): say "let me check" and query.
4. AFTER SESSION: palace_diary_write to record what changed / what to revisit.
5. WHEN FACTS CHANGE: palace_kg_invalidate old, palace_kg_add new.
   Code-structural changes come from the plugin's delta sync — don't hand-author.
"""
