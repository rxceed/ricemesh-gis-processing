import math
from modules.floyd_warshall import run, reconstruct_path


async def floyd_warshall_run_service(
    num_nodes: int,
    edges: list[tuple[int, int, float]],
    directed: bool,
) -> list[list[float | None]]:
    """
    Build the distance matrix and run Floyd-Warshall.

    Returns the all-pairs shortest-path distance matrix.
    math.inf values are converted to None for JSON serialisation.
    """
    dist, _ = run(num_nodes, edges, directed=directed)

    # Replace math.inf with None so the response is JSON-serialisable
    serialisable = [
        [None if d == math.inf else d for d in row]
        for row in dist
    ]
    return serialisable


async def floyd_warshall_reconstruct_service(
    num_nodes: int,
    edges: list[tuple[int, int, float]],
    directed: bool,
    source: int,
    target: int,
) -> tuple[list[int] | None, float | None]:
    """
    Run Floyd-Warshall and reconstruct the shortest path from source to target.

    Returns (path, distance) where path is the ordered list of node indices,
    or (None, None) when the target is unreachable.
    """
    if source >= num_nodes or target >= num_nodes:
        raise ValueError(
            f"source ({source}) or target ({target}) is out of range for {num_nodes} nodes."
        )

    dist, next_node = run(num_nodes, edges, directed=directed)

    path = reconstruct_path(next_node, source, target)

    if path is None:
        return None, None

    distance = dist[source][target]
    distance = None if distance == math.inf else distance
    return path, distance
