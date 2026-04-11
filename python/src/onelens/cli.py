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


if __name__ == "__main__":
    main()
