from fastapi import APIRouter, Body

from server.controllers.floyd_warshall_controller import (
    floyd_warshall_run,
    floyd_warshall_reconstruct,
    floyd_warshall_matrix,
)
from server.schemas.floyd_warshall_schema import (
    floyd_warshall_run_model,
    floyd_warshall_reconstruct_model,
    floyd_warshall_run_response,
    floyd_warshall_reconstruct_response,
    floyd_warshall_matrix_model,
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
