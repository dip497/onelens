"""Neo4j backend — requires Neo4j server running."""

from onelens.graph.db import GraphDB


class Neo4jBackend(GraphDB):
    """Neo4j server backend (JVM-based, requires standalone server or Docker)."""

    def __init__(self, uri: str = "bolt://localhost:7687", user: str = "neo4j", password: str = "neo4j"):
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        with self._driver.session() as session:
            result = session.run(cypher, params or {})
            return [dict(record) for record in result]

    def execute(self, cypher: str, params: dict | None = None) -> None:
        with self._driver.session() as session:
            session.run(cypher, params or {})

    def clear(self) -> None:
        self.execute("MATCH (n) DETACH DELETE n")

    def close(self) -> None:
        self._driver.close()
