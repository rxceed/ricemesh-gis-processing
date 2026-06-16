from fastapi import APIRouter, Body

from server.controllers.floyd_warshall_controller import (
    floyd_warshall_run,
    floyd_warshall_reconstruct,
    floyd_warshall_matrix,
    floyd_warshall_matrix_multi,
    floyd_warshall_chained_routes,
)
from server.schemas.floyd_warshall_schema import (
    floyd_warshall_run_model,
    floyd_warshall_reconstruct_model,
    floyd_warshall_run_response,
    floyd_warshall_reconstruct_response,
    floyd_warshall_matrix_model,
    floyd_warshall_matrix_multi_model,
    floyd_warshall_multi_target_response,
    floyd_warshall_chained_routes_response,
)

floyd_warshall_router = APIRouter(prefix="/api/floydwarshall", tags=["Floyd-Warshall"])


@floyd_warshall_router.post("/run", response_model=floyd_warshall_run_response)
async def run_floyd_warshall(ctx: floyd_warshall_run_model = Body(...)):
    return await floyd_warshall_run(ctx)


@floyd_warshall_router.post("/reconstruct", response_model=floyd_warshall_reconstruct_response)
async def reconstruct_floyd_warshall(ctx: floyd_warshall_reconstruct_model = Body(...)):
    return await floyd_warshall_reconstruct(ctx)


@floyd_warshall_router.post("/matrix", response_model=floyd_warshall_reconstruct_response)
async def matrix_floyd_warshall(ctx: floyd_warshall_matrix_model = Body(...)):
    return await floyd_warshall_matrix(ctx)


@floyd_warshall_router.post("/matrix/multi-target", response_model=floyd_warshall_multi_target_response)
async def matrix_multi_target_floyd_warshall(ctx: floyd_warshall_matrix_multi_model = Body(...)):
    return await floyd_warshall_matrix_multi(ctx)


@floyd_warshall_router.post("/matrix/chained-routes", response_model=floyd_warshall_chained_routes_response)
async def chained_routes_floyd_warshall(ctx: floyd_warshall_matrix_multi_model = Body(...)):
    return await floyd_warshall_chained_routes(ctx)
