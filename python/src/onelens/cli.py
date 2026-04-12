"""OneLens CLI — import, query, and serve code knowledge graphs."""

import click
from pathlib import Path

BACKEND_CHOICES = click.Choice(["falkordb", "falkordblite", "neo4j"])


def _get_db(backend: str, graph: str, db_path: str, **kwargs):
    """Create a graph DB instance from CLI options."""
    from onelens.graph.db import create_backend

    if backend == "falkordblite":
        return create_backend(backend, db_path=str(Path(db_path).expanduser() / graph), graph_name=graph)
    elif backend == "falkordb":
        return create_backend(backend, host=kwargs.get("host", "localhost"), port=kwargs.get("port", 17532), graph_name=graph)
    elif backend == "neo4j":
        return create_backend(backend, uri=kwargs.get("uri", "bolt://localhost:7687"))
    else:
        return create_backend(backend, db_path=str(Path(db_path).expanduser() / graph), graph_name=graph)


@click.group()
@click.version_option()
def main():
    """OneLens - Code Knowledge Graph for Java/Spring Boot"""
    pass


@main.command("import")
@click.argument("export_path", type=click.Path(exists=True, path_type=Path))
@click.option("--graph", default="onelens", help="Graph name")
@click.option("--backend", default="falkordb", type=BACKEND_CHOICES, help="Graph DB backend")
@click.option("--db-path", default="~/.onelens/graphs", help="Base path for embedded graph DBs")
@click.option("--clear", is_flag=True, help="Clear existing graph before import")
def import_graph(export_path: Path, graph: str, backend: str, db_path: str, clear: bool):
    """Import an export JSON (auto-detects full vs delta) into the knowledge graph."""
    import json

    # Auto-detect: full or delta?
    with open(export_path) as f:
        header = json.load(f)  # TODO: stream just the exportType field for large files

    export_type = header.get("exportType", "full")

    db = _get_db(backend, graph, db_path)

    if export_type == "delta":
        from onelens.importer.delta_loader import DeltaLoader
        loader = DeltaLoader(db)
        stats = loader.apply_delta(export_path)
        click.echo(f"Delta applied: {stats}")
    else:
        from onelens.importer.loader import GraphLoader
        loader = GraphLoader(db)
        if clear:
            loader.clear()
        stats = loader.load_full(export_path)
        click.echo(f"Full import: {stats}")


@main.command()
@click.argument("delta_path", type=click.Path(exists=True, path_type=Path))
@click.option("--graph", default="onelens")
@click.option("--backend", default="falkordb", type=BACKEND_CHOICES)
@click.option("--db-path", default="~/.onelens/graphs")
def delta(delta_path: Path, graph: str, backend: str, db_path: str):
    """Apply a delta export to an existing graph."""
    from onelens.importer.delta_loader import DeltaLoader

    db = _get_db(backend, graph, db_path)
    loader = DeltaLoader(db)
    stats = loader.apply_delta(delta_path)
    click.echo(f"Delta applied: {stats}")


@main.command()
@click.option("--graph", default="onelens")
@click.option("--backend", default="falkordb", type=BACKEND_CHOICES)
@click.option("--db-path", default="~/.onelens/graphs")
def stats(graph: str, backend: str, db_path: str):
    """Show graph statistics."""
    db = _get_db(backend, graph, db_path)
    db.print_stats()


@main.command()
@click.argument("cypher")
@click.option("--graph", default="onelens")
@click.option("--backend", default="falkordb", type=BACKEND_CHOICES)
@click.option("--db-path", default="~/.onelens/graphs")
def query(cypher: str, graph: str, backend: str, db_path: str):
    """Run a Cypher query against the graph."""
    from rich.table import Table
    from rich.console import Console

    db = _get_db(backend, graph, db_path)
    result = db.query(cypher)

    console = Console()
    if result:
        table = Table()
        for col in result[0].keys():
            table.add_column(col)
        for row in result[:100]:
            table.add_row(*[str(v) for v in row.values()])
        console.print(table)
        if len(result) > 100:
            console.print(f"[dim]... {len(result) - 100} more rows (showing 100/{len(result)})[/dim]")
    else:
        console.print("[dim]No results[/dim]")


@main.command()
@click.option("--graph", default="onelens")
@click.option("--backend", default="falkordb", type=BACKEND_CHOICES)
@click.option("--db-path", default="~/.onelens/graphs")
def serve(graph: str, backend: str, db_path: str):
    """Start the MCP server for AI tools."""
    from onelens.mcp.server import create_server

    db = _get_db(backend, graph, db_path)
    server = create_server(db)
    server.run()


@main.command("search")
@click.argument("term")
@click.option("--type", "node_type", type=click.Choice(["class", "method", "endpoint"]), default=None,
              help="Filter by node type (omit to search all)")
@click.option("--graph", default="onelens")
@click.option("--backend", default="falkordb", type=BACKEND_CHOICES)
@click.option("--db-path", default="~/.onelens/graphs")
def search(term: str, node_type: str | None, graph: str, backend: str, db_path: str):
    """Search code by name using full-text search.

    Supports prefix (User*), fuzzy (%auth%1), and exact matching.
    """
    from onelens.graph.analysis import search_code
    from rich.table import Table
    from rich.console import Console

    db = _get_db(backend, graph, db_path)
    results = search_code(db, term, node_type or "")

    console = Console()
    if not results:
        console.print(f"[dim]No results for '{term}'[/dim]")
        return

    table = Table(title=f"Search: {term}")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("FQN", style="white")
    table.add_column("File", style="dim")
    for r in results[:50]:
        table.add_row(r.get("type", ""), r.get("name", ""), r.get("fqn", ""), r.get("file", ""))
    console.print(table)
    if len(results) > 50:
        console.print(f"[dim]... showing 50/{len(results)} results[/dim]")


@main.command("trace")
@click.argument("target")
@click.option("--type", "entry_type", type=click.Choice(["method", "endpoint"]), default="method",
              help="Target type: method FQN or endpoint path")
@click.option("--depth", default=5, type=click.IntRange(1, 5), help="Max call depth (1-5)")
@click.option("--http-method", default="", help="HTTP method filter (GET, POST, etc.)")
@click.option("--include-external", is_flag=True, help="Include external library calls")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON (for AI consumption)")
@click.option("--graph", default="onelens")
@click.option("--backend", default="falkordb", type=BACKEND_CHOICES)
@click.option("--db-path", default="~/.onelens/graphs")
def trace(target: str, entry_type: str, depth: int, http_method: str,
          include_external: bool, as_json: bool, graph: str, backend: str, db_path: str):
    """Trace execution flow from an entry point through the call chain.

    TARGET is a method FQN or endpoint path.
    """
    import json as json_mod
    from onelens.graph.analysis import get_flow_trace, get_endpoint_flow

    db = _get_db(backend, graph, db_path)

    if entry_type == "endpoint":
        results = get_endpoint_flow(db, target, http_method, depth, include_external)
    else:
        results = get_flow_trace(db, target, depth, include_external)

    if not results:
        click.echo("No results — check the target FQN/path")
        return

    if as_json:
        click.echo(json_mod.dumps(results, indent=2))
        return

    # Compact output: endpoint info at depth 0, then indented call chain
    for r in results:
        d = r.get("depth", 0)
        indent = "  " * d
        cls = r.get("class", "")
        method = r.get("method", "")
        loc = r.get("location", "")
        ep = r.get("endpoint", "")

        # Show endpoint before handler at depth 0
        prefix = f"{ep} → " if ep else ""
        loc_info = f"  {loc}" if loc else ""
        click.echo(f"{indent}{prefix}{cls}.{method}{loc_info}")

    # Summary
    classes = {r.get("class", "") for r in results if r.get("class")}
    max_depth = max((r.get("depth", 0) for r in results), default=0)
    click.echo(f"\n{len(results)} methods across {len(classes)} classes, max depth {max_depth}")


@main.command("entry-points")
@click.option("--graph", default="onelens")
@click.option("--backend", default="falkordb", type=BACKEND_CHOICES)
@click.option("--db-path", default="~/.onelens/graphs")
def entry_points(graph: str, backend: str, db_path: str):
    """List all entry points (REST endpoints, scheduled methods, main())."""
    from onelens.graph.analysis import get_entry_points
    from rich.table import Table
    from rich.console import Console

    db = _get_db(backend, graph, db_path)
    results = get_entry_points(db)

    console = Console()
    if not results:
        console.print("[dim]No entry points found[/dim]")
        return

    table = Table(title="Entry Points")
    table.add_column("Type", style="cyan")
    table.add_column("Entry", style="green")
    table.add_column("Method FQN", style="white")
    for r in results:
        table.add_row(r.get("type", ""), r.get("entry", ""), r.get("methodFqn", ""))
    console.print(table)
    console.print(f"[dim]{len(results)} entry points[/dim]")


@main.command("impact")
@click.argument("method_fqn")
@click.option("--depth", default=5, type=click.IntRange(1, 5), help="Max caller depth (1-5)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--graph", default="onelens")
@click.option("--backend", default="falkordb", type=BACKEND_CHOICES)
@click.option("--db-path", default="~/.onelens/graphs")
def impact(method_fqn: str, depth: int, as_json: bool, graph: str, backend: str, db_path: str):
    """Find all REST endpoints affected if this method changes.

    Traces UP from the method through callers to find endpoint handlers.
    Answers: "which user-facing APIs break if I change this?"
    """
    import json as json_mod
    from onelens.graph.analysis import get_impacted_endpoints

    db = _get_db(backend, graph, db_path)
    results = get_impacted_endpoints(db, method_fqn, depth)

    if not results:
        click.echo("No impacted endpoints found (method may not be reachable from any endpoint)")
        return

    if as_json:
        click.echo(json_mod.dumps(results, indent=2))
        return

    for r in results:
        ep = r.get("endpoint", "")
        ctrl = r.get("controller", "")
        handler = r.get("handler", "")
        loc = r.get("location", "")
        hops = r.get("hops", 0)
        click.echo(f"{ep}  →  {ctrl}.{handler}  {loc}  ({hops} hops)")

    click.echo(f"\n{len(results)} endpoints affected")


if __name__ == "__main__":
    main()
