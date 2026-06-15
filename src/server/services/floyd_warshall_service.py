import math
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
