from fastapi import HTTPException

from server.schemas.floyd_warshall_schema import (
    floyd_warshall_run_model,
    floyd_warshall_reconstruct_model,
    floyd_warshall_run_response,
    floyd_warshall_reconstruct_response,
)
from server.services.floyd_warshall_service import (
    floyd_warshall_run_service,
    floyd_warshall_reconstruct_service,
)


async def floyd_warshall_run(ctx: floyd_warshall_run_model) -> floyd_warshall_run_response:
    try:
        dist = await floyd_warshall_run_service(
            ctx.num_nodes,
            ctx.edges,
            ctx.directed,
        )
        return floyd_warshall_run_response(dist=dist)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def floyd_warshall_reconstruct(
    ctx: floyd_warshall_reconstruct_model,
) -> floyd_warshall_reconstruct_response:
    try:
        path, distance = await floyd_warshall_reconstruct_service(
            ctx.num_nodes,
            ctx.edges,
            ctx.directed,
            ctx.source,
            ctx.target,
        )
        return floyd_warshall_reconstruct_response(
            source=ctx.source,
            target=ctx.target,
            path=path,
            distance=distance,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
