from fastapi import HTTPException

from server.schemas.floyd_warshall_schema import (
    floyd_warshall_run_model,
    floyd_warshall_reconstruct_model,
    floyd_warshall_run_response,
    floyd_warshall_reconstruct_response,
    floyd_warshall_matrix_model,
    floyd_warshall_matrix_multi_model,
    floyd_warshall_multi_target_response,
    floyd_warshall_target_route,
    floyd_warshall_chained_routes_response,
)
from server.services.floyd_warshall_service import (
    floyd_warshall_run_service,
    floyd_warshall_reconstruct_service,
    floyd_warshall_matrix_service,
    floyd_warshall_matrix_multi_service,
    floyd_warshall_chained_routes_service,
)


def _extract_node_edges(ctx) -> list[tuple[int, int, str, str]]:
    """Convert node_edge_model list to (u, v, centroid_u, centroid_v) tuples."""
    return [
        (e.u, e.v, e.centroid_u, e.centroid_v)
        for e in ctx.edges
    ]


def _extract_nodes(ctx) -> list[dict]:
    """Convert node_point_model list to plain dicts."""
    return [n.model_dump() for n in ctx.nodes]


async def floyd_warshall_run(ctx: floyd_warshall_run_model) -> floyd_warshall_run_response:
    try:
        dist, successor = await floyd_warshall_run_service(
            ctx.num_nodes,
            _extract_nodes(ctx),
            _extract_node_edges(ctx),
            ctx.directed,
        )
        return floyd_warshall_run_response(dist=dist, successor=successor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def floyd_warshall_reconstruct(
    ctx: floyd_warshall_reconstruct_model,
) -> floyd_warshall_reconstruct_response:
    try:
        path, weight = await floyd_warshall_reconstruct_service(
            ctx.num_nodes,
            _extract_nodes(ctx),
            _extract_node_edges(ctx),
            ctx.directed,
            ctx.source,
            ctx.target,
        )
        return floyd_warshall_reconstruct_response(
            source=ctx.source,
            target=ctx.target,
            path=path,
            weight=weight,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def floyd_warshall_matrix(
    ctx: floyd_warshall_matrix_model,
) -> floyd_warshall_reconstruct_response:
    try:
        path, weight = await floyd_warshall_matrix_service(
            ctx.matrix,
            ctx.successor,
            ctx.source,
            ctx.target,
        )
        return floyd_warshall_reconstruct_response(
            source=ctx.source,
            target=ctx.target,
            path=path,
            weight=weight,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def floyd_warshall_matrix_multi(
    ctx: floyd_warshall_matrix_multi_model,
) -> floyd_warshall_multi_target_response:
    try:
        routes_raw = await floyd_warshall_matrix_multi_service(
            ctx.matrix,
            ctx.successor,
            ctx.source,
        )
        routes = [
            floyd_warshall_target_route(
                target=r["target"],
                path=r["path"],
                weight=r["weight"],
            )
            for r in routes_raw
        ]
        return floyd_warshall_multi_target_response(source=ctx.source, routes=routes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def floyd_warshall_chained_routes(
    ctx: floyd_warshall_matrix_multi_model,
) -> floyd_warshall_chained_routes_response:
    try:
        routes_raw = await floyd_warshall_chained_routes_service(
            ctx.matrix,
            ctx.successor,
            ctx.source,
        )
        routes = [
            floyd_warshall_target_route(
                target=r["target"],
                path=r["path"],
                weight=r["weight"],
            )
            for r in routes_raw
        ]
        return floyd_warshall_chained_routes_response(source=ctx.source, routes=routes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
