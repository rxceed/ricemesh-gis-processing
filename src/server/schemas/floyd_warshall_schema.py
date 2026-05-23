from pydantic import BaseModel, Field
from typing import Optional


class floyd_warshall_run_model(BaseModel):
    num_nodes: int = Field(..., gt=0, description="Total number of nodes (0-indexed)")
    edges: list[tuple[int, int, float]] = Field(
        ..., description="List of (u, v, weight) edge tuples"
    )
    directed: bool = Field(True, description="Treat edges as directed when True")


class floyd_warshall_reconstruct_model(BaseModel):
    num_nodes: int = Field(..., gt=0, description="Total number of nodes (0-indexed)")
    edges: list[tuple[int, int, float]] = Field(
        ..., description="List of (u, v, weight) edge tuples"
    )
    directed: bool = Field(True, description="Treat edges as directed when True")
    source: int = Field(..., ge=0, description="Source node index")
    target: int = Field(..., ge=0, description="Target node index")


class floyd_warshall_run_response(BaseModel):
    dist: list[list[Optional[float]]]


class floyd_warshall_reconstruct_response(BaseModel):
    source: int
    target: int
    path: Optional[list[int]]
    distance: Optional[float]
