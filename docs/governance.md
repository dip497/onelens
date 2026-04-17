# Governance

How decisions are made today, and how that will evolve.

## Current (pre-1.0)

- **BDFL-led.** The project maintainer (OneLens Contributors,
  current BDFL: `griflet` on GitHub) is the benevolent dictator
  through 1.0. Architectural decisions, roadmap, releases, and
  merge authority all rest there.
- **Issue-driven RFCs.** Larger proposals (new concept, new seam,
  breaking change, new language support) require an issue
  labelled `rfc:` with problem, proposal, alternatives, and
  migration path. Comment period: one week before implementation
  PRs merge.
- **PRs welcome, issue-first for non-trivial changes.** Small
  bug fixes and doc improvements can open PRs directly.
- **Releases.** Semantic versioning. Every tagged release has a
  CHANGELOG entry and passes CI.

## Post-1.0 (indicative)

- **Invite 2–3 co-maintainers** when the project reaches real
  adoption (roughly 100 stars, 10 public adopters, or one
  enterprise user publicly citing OneLens).
- **Maintainer council.** Core decisions require a majority; BDFL
  retains veto on direction-setting items only.
- **RFC repo** if issue-based RFCs no longer scale.

## Long-term

- **Foundation.** When five or more unrelated organisations depend
  on the project, move spec documents (JSON export schema, MCP
  tool contracts) to a neutral foundation.

## Commercial entity

If and when a paid offering is introduced: core (plugin + CLI +
importer + retrieval + skill) remains OSS forever, dual
MIT / Apache-2.0. Paid offerings are net-new, separate repo,
separate licence. No rug-pulls.

## Code of conduct

See [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md).
