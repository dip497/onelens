"""Release snapshot producer + consumer.

See `docs/design/phase-r-release-snapshots.md` for the design and
`skills/onelens/references/recipes.md` #16 for the query patterns.
"""

from onelens.snapshots import consumer, publisher

__all__ = ["publisher", "consumer"]
