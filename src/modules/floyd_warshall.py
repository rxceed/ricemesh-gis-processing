import math
from typing import Optional
from argparse import ArgumentParser as _ArgumentParser

# Sentinel value representing no direct edge between two nodes
_INF = math.inf

def calculate_weight(source: dict, dest: dict, distance):
    """
    Calculate weight of the node

    Parameters
    ----------
    source      : dictionary containing property of the source plot {area, water_height, optimal_heigth, elevation}
    dest        : dictionary containing property of the destination {area, water_height, optimal_heigth, elevation}
    distance    : euclidean distance of the two centroids
    Returns
    -------
    dist : num_nodes × num_nodes distance matrix
    """
    v_source = source["area"]*source["water_height"]
    v_deficit_dest = dest["area"]*max(0, dest["water_height"]-dest["optimal_height"])
    e = 1
    source_cost = 1/(v_source+e)
    dest_cost = 1/(v_deficit_dest+e)
    delta_elevation = dest["elevation"]-source["elevation"]
    if delta_elevation <= 0:
        E_ij = 1
    else:
        E_ij = 100*delta_elevation
    weight = (distance*E_ij)*(source_cost*(source_cost/dest_cost+source_cost)+dest_cost*(dest_cost/source_cost+dest_cost))
    return weight

def build_distance_matrix(
    num_nodes: int,
    edges: list[tuple[int, int, float]],
    directed: bool = True,
) -> list[list[float]]:
    """
    Build an initial distance matrix from a list of edges.

    Parameters
    ----------
    num_nodes : total number of nodes (nodes are 0-indexed)
    edges     : list of (u, v, weight) tuples representing graph edges
    directed  : if False, each edge is added in both directions

    Returns
    -------
    dist : num_nodes × num_nodes distance matrix
    """
    dist = [[_INF] * num_nodes for _ in range(num_nodes)]

    # Zero-cost self-loops
    for i in range(num_nodes):
        dist[i][i] = 0.0

    for u, v, weight in edges:
        if u < 0 or u >= num_nodes or v < 0 or v >= num_nodes:
            raise ValueError(
                f"Edge ({u}, {v}) references a node outside the valid range [0, {num_nodes - 1}]."
            )
        if weight < 0:
            raise ValueError(
                f"Negative edge weight {weight} on edge ({u}, {v}) is not supported."
            )

        dist[u][v] = min(dist[u][v], weight)

        if not directed:
            dist[v][u] = min(dist[v][u], weight)

    return dist


def build_distance_matrix_from_node_data(
    num_nodes: int,
    nodes: list[dict],
    node_edges: list[tuple[int, int, float]],
    directed: bool = True,
) -> list[list[float]]:
    """
    Build an initial distance matrix by computing edge weights from node properties.

    Parameters
    ----------
    num_nodes  : total number of nodes (0-indexed)
    nodes      : list of node property dicts, indexed by node id.
                 Each dict must contain: area, water_height, optimal_height, elevation
    node_edges : list of (u, v, distance) where distance is the euclidean distance
                 between the two node centroids
    directed   : if False, each edge is added in both directions

    Returns
    -------
    dist : num_nodes × num_nodes distance matrix
    """
    if len(nodes) != num_nodes:
        raise ValueError(
            f"Length of nodes ({len(nodes)}) must equal num_nodes ({num_nodes})."
        )

    # Convert (u, v, distance) -> (u, v, weight) using calculate_weight
    weighted_edges: list[tuple[int, int, float]] = []
    for u, v, distance in node_edges:
        if u < 0 or u >= num_nodes or v < 0 or v >= num_nodes:
            raise ValueError(
                f"Edge ({u}, {v}) references a node outside the valid range [0, {num_nodes - 1}]."
            )
        weight = calculate_weight(nodes[u], nodes[v], distance)
        weighted_edges.append((u, v, weight))

    return build_distance_matrix(num_nodes, weighted_edges, directed=directed)


def floyd_warshall(
    dist: list[list[float]],
) -> tuple[list[list[float]], list[list[Optional[int]]]]:
    """
    Run Floyd-Warshall all-pairs shortest path on a distance matrix.

    Parameters
    ----------
    dist : n × n distance matrix where dist[i][j] is the direct edge cost
            from node i to node j, or math.inf when no direct edge exists.
            Self-loops (dist[i][i]) must be 0.

    Returns
    -------
    dist : updated n × n matrix with shortest-path distances after relaxation
    next_node : n × n matrix for path reconstruction.
                next_node[i][j] is the first hop from i on the shortest path to j,
                or None when j is unreachable from i.

    Raises
    ------
    ValueError : if a negative-weight cycle is detected (dist[i][i] < 0 after relaxation)
    """
    n = len(dist)

    # Validate square matrix
    for row in dist:
        if len(row) != n:
            raise ValueError("Distance matrix must be square (n × n).")

    # Deep copy so the original matrix is not mutated
    dist = [row[:] for row in dist]

    # Initialise next_node for path reconstruction
    next_node: list[list[Optional[int]]] = [[None] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if dist[i][j] < _INF and i != j:
                next_node[i][j] = j

    # Main relaxation: try every intermediate node k
    for k in range(n):
        for i in range(n):
            for j in range(n):
                via_k = dist[i][k] + dist[k][j]
                if via_k < dist[i][j]:
                    dist[i][j] = via_k
                    next_node[i][j] = next_node[i][k]

    # Detect negative-weight cycles
    for i in range(n):
        if dist[i][i] < 0:
            raise ValueError(
                f"Negative-weight cycle detected involving node {i}."
            )

    return dist, next_node


def reconstruct_path(
    next_node: list[list[Optional[int]]],
    source: int,
    target: int,
) -> Optional[list[int]]:
    """
    Reconstruct the shortest path between source and target using the
    next_node matrix produced by floyd_warshall.

    Parameters
    ----------
    next_node : n × n successor matrix from floyd_warshall
    source    : starting node index
    target    : destination node index

    Returns
    -------
    path : ordered list of node indices from source to target (inclusive),
            or None if target is unreachable from source
    """
    if next_node[source][target] is None:
        return None

    path = [source]
    current = source

    # Walk successor pointers until we reach the target
    while current != target:
        current = next_node[current][target]
        if current is None:
            # Broken path — should not happen with a valid next_node matrix
            return None
        path.append(current)

    return path


def run(
    num_nodes: int,
    edges: list[tuple[int, int, float]],
    directed: bool = True,
) -> tuple[list[list[float]], list[list[Optional[int]]]]:
    """
    Convenience wrapper: build the distance matrix and run Floyd-Warshall.

    Parameters
    ----------
    num_nodes : total number of nodes (0-indexed)
    edges     : list of (u, v, weight) tuples
    directed  : if False, edges are treated as undirected

    Returns
    -------
    dist      : all-pairs shortest-path distance matrix
    next_node : successor matrix for path reconstruction
    """
    dist = build_distance_matrix(num_nodes, edges, directed=directed)
    return floyd_warshall(dist)


def run_from_node_data(
    num_nodes: int,
    nodes: list[dict],
    node_edges: list[tuple[int, int, float]],
    directed: bool = True,
) -> tuple[list[list[float]], list[list[Optional[int]]]]:
    """
    Convenience wrapper: compute weights from node data, build distance matrix,
    and run Floyd-Warshall.

    Parameters
    ----------
    num_nodes  : total number of nodes (0-indexed)
    nodes      : list of node property dicts (area, water_height, optimal_height, elevation)
    node_edges : list of (u, v, distance) tuples
    directed   : if False, edges are treated as undirected

    Returns
    -------
    dist      : all-pairs shortest-path distance matrix
    next_node : successor matrix for path reconstruction
    """
    dist = build_distance_matrix_from_node_data(num_nodes, nodes, node_edges, directed=directed)
    return floyd_warshall(dist)

if __name__ == "__main__":
    # arg_parser = _ArgumentParser()
    # arg_parser.add_argument("input", type=str, help="file path to input video relative to working directory")
    # arg_parser.add_argument("-s", "--start-sec", type=float, help="starting point of the video that want to be parsed in seconds")
    # arg_parser.add_argument("-e","--end-sec", type=float, help="ending point of the video that want to be parsed in seconds")
    # arg_parser.add_argument("-f", "--frame-interval", type=int, help="frame interval of the parser")
    # arg_parser.add_argument("-c", "--compression", type=int, help="image PNG compression on a scale from 0 (no compression) to 9 (max compression)")
    # arg_parser.add_argument("--resize", type=str, help="resize the frames to the specified dimensions in WxH (e.g., 1920x1080)")
    # args = arg_parser.parse_args()
    print("Y")