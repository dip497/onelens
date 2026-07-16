"""Tunnels + graph stats over ChromaDB metadata (MemPalace palace_graph.py parity)."""

from __future__ import annotations

from collections import defaultdict

from . import store, taxonomy


def find_tunnels(
    wing_a: str | None = None,
    wing_b: str | None = None,
    *,
    min_shared: int = 1,
) -> list[dict]:
    rooms = taxonomy._scan()["rooms"]  # {(wing, room): count}
    by_room: dict[str, dict[str, int]] = defaultdict(dict)
    for (w, r), c in rooms.items():
        by_room[r][w] = c

    tunnels: list[dict] = []
    fq = taxonomy.fqn_samples()
    for room, wings_map in by_room.items():
        if len(wings_map) < 2:
            continue
        if wing_a and wing_a not in wings_map:
            continue
        if wing_b and wing_b not in wings_map:
            continue
        shared = sum(wings_map.values())
        if shared < min_shared:
            continue
        samples: list[str] = []
        for w in wings_map:
            samples.extend(fq.get((w, room), []))
        tunnels.append(
            {
                "room": room,
                "wings": sorted(wings_map.keys()),
                "shared_drawer_count": shared,
                "sample_fqns": samples[:5],
            }
        )
    tunnels.sort(key=lambda t: -t["shared_drawer_count"])
    return tunnels


def graph_stats() -> dict:
    wings = taxonomy.wing_counts()
    rooms = taxonomy._scan()["rooms"]
    rooms_per_wing: dict[str, int] = defaultdict(int)
    for (w, _r) in rooms:
        rooms_per_wing[w] += 1
    tunnels_all = find_tunnels()

    # Sum edge counts across code graphs (best-effort; Entity/ASSERTS counted separately).
    edge_counts: dict[str, int] = defaultdict(int)
    for wing in wings:
        try:
            db = store.get_graph_db(wing)
            res = db.query("MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n")
            for row in res or []:
                edge_counts[row["t"]] += int(row["n"])
        except Exception:
            continue

    return {
        "total_rooms": len(rooms),
        "tunnel_rooms": len(tunnels_all),
        "total_edges": sum(edge_counts.values()),
        "total_edges_by_type": dict(edge_counts),
        "rooms_per_wing": dict(rooms_per_wing),
        "top_tunnels": tunnels_all[:5],
    }
