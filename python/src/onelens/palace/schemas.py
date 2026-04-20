"""Pydantic return types. Field names mirror MemPalace where they overlap."""

from __future__ import annotations

from pydantic import BaseModel


class DrawerRef(BaseModel):
    drawer_id: str
    wing: str
    room: str
    hall: str | None = None
    fqn: str | None = None
    snippet: str
    score: float
    source: str = "main"  # main | notes | diary


class DuplicateMatch(BaseModel):
    id: str
    wing: str
    room: str
    similarity: float
    content: str


class DuplicateReport(BaseModel):
    is_duplicate: bool
    matches: list[DuplicateMatch]


class TripleRef(BaseModel):
    triple_id: str
    created: bool
    valid_from: str | None
    valid_to: str | None


class TripleHit(BaseModel):
    subject: str
    predicate: str
    object: str
    valid_from: str | None = None
    valid_to: str | None = None
    confidence: float = 1.0
    source: str = "sidecar"  # sidecar | structural
    wing: str | None = None


class TimelineEvent(BaseModel):
    ts: str
    event: str  # asserted | ended | diary
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    wing: str | None = None
    source: str = "kg"


class Tunnel(BaseModel):
    room: str
    wings: list[str]
    shared_drawer_count: int
    sample_fqns: list[str] = []


class PathNode(BaseModel):
    label: str
    fqn: str | None = None
    name: str | None = None
    wing: str | None = None


class PathEdge(BaseModel):
    type: str
    props: dict = {}


class PathHit(BaseModel):
    nodes: list[PathNode]
    edges: list[PathEdge]


class DiaryEntry(BaseModel):
    ts: str
    topic: str
    entry: str
    importance: float = 1.0
