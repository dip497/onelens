"""Base class for SubdocLoaders — one per graph subsystem, owning BOTH import paths."""


class SubdocLoader:
    """One graph subsystem, owning BOTH import paths so they cannot diverge.

    json_key is the top-level export key this loader reads.
    """

    json_key: str = ""

    def load_full(self, writer, progress, data: dict, wing: str) -> None:
        """Full import path: write nodes + edges into the graph via writer."""
        ...

    def apply_delta(self, writer, upserted: dict, wing: str) -> None:
        """Delta import path: MERGE/DELETE/recreate for changed targets."""
        ...
