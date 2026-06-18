import math
import heapq
from modules.floyd_warshall import run_from_node_data, reconstruct_path, floyd_warshall
from utils.geometry import decode_point_4326

_EARTH_RADIUS_M = 6_371_000.0

def _EWKT_to_point(raw_ewkt: str) -> tuple[float, float]:
    lon, lat = decode_point_4326(raw_ewkt)
    return lon, lat

def _haversine_distance(
    centroid_u: tuple[float, float],
    centroid_v: tuple[float, float],
) -> float:
    """
    Compute great-circle distance in metres between two (lon, lat) points.

    Parameters
    ----------
    centroid_u : (longitude, latitude) of the source node centroid in decimal degrees
    centroid_v : (longitude, latitude) of the destination node centroid in decimal degrees
    """
    lon1, lat1 = map(math.radians, centroid_u)
    lon2, lat2 = map(math.radians, centroid_v)

    d_lat = lat2 - lat1
    d_lon = lon2 - lon1

    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return _EARTH_RADIUS_M * 2 * math.asin(math.sqrt(a))


def _centroid_edges_to_distance_edges(
    node_edges: list[tuple[int, int, str, str]],
) -> list[tuple[int, int, float]]:
    """Convert (u, v, centroid_u, centroid_v) tuples to (u, v, distance_m) tuples."""
    result = []
    for u, v, centroid_u, centroid_v in node_edges:
        point_u = _EWKT_to_point(centroid_u)
        point_v = _EWKT_to_point(centroid_v)
        distance = _haversine_distance(point_u, point_v)
        if distance <= 0:
            raise ValueError(
                f"Computed distance between centroids of edge ({u}, {v}) is zero or negative. "
                "Ensure the two centroid points are distinct."
            )
        result.append((u, v, distance))
    return result


async def floyd_warshall_run_service(
    num_nodes: int,
    nodes: list[dict],
    node_edges: list[tuple[int, int, str, str]],
    directed: bool,
) -> tuple[list[list[float | None]], list[list[int | None]]]:
    """
    Convert centroid geometry points to distances, build the distance matrix,
    and run Floyd-Warshall.

    Returns the all-pairs shortest-path distance matrix and successor matrix.
    math.inf values are converted to None for JSON serialisation.
    """
    # Convert centroid pairs → haversine distances before passing to the module
    distance_edges = _centroid_edges_to_distance_edges(node_edges)
    dist, next_node = run_from_node_data(num_nodes, nodes, distance_edges, directed=directed)

    # Replace math.inf with None so the response is JSON-serialisable
    serialisable = [
        [None if d == math.inf else d for d in row]
        for row in dist
    ]
    return serialisable, next_node


async def floyd_warshall_reconstruct_service(
    num_nodes: int,
    nodes: list[dict],
    node_edges: list[tuple[int, int, str, str]],
    directed: bool,
    source: int,
    target: int,
) -> tuple[list[int] | None, float | None]:
    """
    Convert centroid geometry points to distances, run Floyd-Warshall, and
    reconstruct the shortest path from source to target.

    Returns (path, distance) where path is the ordered list of node indices,
    or (None, None) when the target is unreachable.
    """
    if source >= num_nodes or target >= num_nodes:
        raise ValueError(
            f"source ({source}) or target ({target}) is out of range for {num_nodes} nodes."
        )

    # Convert centroid pairs → haversine distances before passing to the module
    distance_edges = _centroid_edges_to_distance_edges(node_edges)
    dist, next_node = run_from_node_data(num_nodes, nodes, distance_edges, directed=directed)

    path = reconstruct_path(next_node, source, target)

    if path is None:
        return None, None

    distance = dist[source][target]
    distance = None if distance == math.inf else distance
    return path, distance


async def floyd_warshall_matrix_service(
    matrix: list[list[float | None]],
    successor: list[list[int | None]],
    source: int,
    target: int,
) -> tuple[list[int] | None, float | None]:
    """
    Reconstruct path and weight using already provided distance matrix and successor matrix.
    """
    path = reconstruct_path(successor, source, target)
    weight = None
    if path is not None:
        weight = matrix[source][target]
        if weight == math.inf:
            weight = None
    return path, weight


async def floyd_warshall_matrix_multi_service(
    matrix: list[list[float | None]],
    successor: list[list[int | None]],
    source: int,
) -> list[dict]:
    """
    Find the most efficient route from source to every reachable target node.

    Iterates all candidate targets (all nodes except source), reconstructs each
    path via the precomputed matrix and successor, then returns only reachable
    targets sorted by ascending weight.

    Returns a list of dicts with keys: target, path, weight.
    """
    n = len(matrix)

    if source >= n:
        raise ValueError(f"Source index {source} is out of bounds for matrix of size {n}.")

    routes = []
    for target in range(n):
        # Skip self-route
        if target == source:
            continue

        path = reconstruct_path(successor, source, target)

        # Skip unreachable targets
        if path is None:
            continue

        weight = matrix[source][target]
        if weight is None or weight == math.inf:
            continue

        routes.append({"target": target, "path": path, "weight": weight})

    # Sort by weight ascending — smallest cost routes come first
    routes.sort(key=lambda r: r["weight"])

    return routes


async def floyd_warshall_chained_routes_service(
    matrix: list[list[float | None]],
    successor: list[list[int | None]],
    source: int,
) -> list[dict]:
    """
    Find the most efficient chained routes from source to every reachable target,
    including targets that are unreachable directly from source but reachable via
    an intermediate hop (e.g. A→B→D where A cannot reach D directly).

    Uses a Dijkstra-style min-heap so that:
    - Nodes are settled in order of cheapest known chained cost from source.
    - Once a node is settled, its cost and path are guaranteed optimal.
    - When a node is settled it becomes a valid hop; its Floyd-Warshall
      outgoing legs are explored to discover further (possibly unreachable-from-
      source) targets via chaining.

    Chaining: chained_weight = weight[source→hop] + weight[hop→new_target]
              chained_path   = path[source→hop] + path[hop→new_target][1:]

    Returns a list of dicts with keys: target, path, weight.
    Sorted by ascending weight.
    """
    n = len(matrix)

    if source >= n:
        raise ValueError(f"Source index {source} is out of bounds for matrix of size {n}.")

    def _cost(i: int, j: int) -> float:
        """Return matrix cost, treating None as inf."""
        v = matrix[i][j]
        return math.inf if v is None else v

    def _join_paths(path_a: list[int], path_b: list[int]) -> list[int]:
        """Concatenate two sub-paths, removing the duplicate shared middle node."""
        return path_a + path_b[1:]

    # best_weight[t] → lowest total chained cost found so far to reach target t
    # best_path[t]   → corresponding full chained path
    best_weight: dict[int, float] = {}
    best_path: dict[int, list[int]] = {}

    # settled: nodes whose optimal cost is finalised (first pop from heap)
    settled: set[int] = set()

    # Min-heap entries: (total_cost, node, path_so_far)
    # Seed with direct Floyd-Warshall legs from source
    heap: list[tuple[float, int, list[int]]] = []

    for candidate in range(n):
        if candidate == source:
            continue
        w = _cost(source, candidate)
        if w == math.inf:
            continue
        path = reconstruct_path(successor, source, candidate)
        if path is None:
            continue
        heapq.heappush(heap, (w, candidate, path))

    while heap:
        cost, hop, path = heapq.heappop(heap)

        # Skip stale heap entries — node already settled with a cheaper cost
        if hop in settled:
            continue

        # Settle this node: its chained cost from source is now optimal
        settled.add(hop)
        best_weight[hop] = cost
        best_path[hop] = path

        # Explore Floyd-Warshall legs from hop to discover further targets
        for new_target in range(n):
            if new_target == source or new_target in settled:
                continue

            leg_weight = _cost(hop, new_target)
            if leg_weight == math.inf:
                continue

            leg_path = reconstruct_path(successor, hop, new_target)
            if leg_path is None:
                continue

            chained_cost = cost + leg_weight
            chained_path = _join_paths(path, leg_path)

            # Push to heap; stale entries are discarded on pop via settled check
            heapq.heappush(heap, (chained_cost, new_target, chained_path))

    routes = [
        {"target": t, "path": best_path[t], "weight": best_weight[t]}
        for t in best_weight
    ]
    routes.sort(key=lambda r: r["weight"])
    return routes
