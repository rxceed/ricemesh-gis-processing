from pydantic import BaseModel, Field, model_validator
from typing import Optional, Annotated


class node_point_model(BaseModel):
    area: float = Field(..., gt=0, description="Area of the plot in m²")
    water_height: float = Field(..., ge=0, description="Current water height in m")
    optimal_height: float = Field(..., ge=0, description="Optimal water height in m")
    elevation: float = Field(..., description="Elevation of the plot in m")

class node_edge_model(BaseModel):
    u: int = Field(..., ge=0, description="Source node index (0-indexed)")
    v: int = Field(..., ge=0, description="Destination node index (0-indexed)")
    centroid_u: str = Field(..., description="Geometry centroid point (EWKT) of the source node")
    centroid_v: str = Field(..., description="Geometry centroid point (EWKT) of the destination node")


class floyd_warshall_run_model(BaseModel):
    num_nodes: int = Field(..., gt=0, description="Total number of nodes (0-indexed)")
    nodes: list[node_point_model] = Field(
        ..., description="List of node properties indexed by node id"
    )
    edges: list[node_edge_model] = Field(
        ..., description="List of edges with source, destination, and centroid geometry points"
    )
    directed: bool = Field(True, description="Treat edges as directed when True")


class floyd_warshall_reconstruct_model(BaseModel):
    num_nodes: int = Field(..., gt=0, description="Total number of nodes (0-indexed)")
    nodes: list[node_point_model] = Field(
        ..., description="List of node properties indexed by node id"
    )
    edges: list[node_edge_model] = Field(
        ..., description="List of edges with source, destination, and centroid geometry points"
    )
    directed: bool = Field(True, description="Treat edges as directed when True")
    source: int = Field(..., ge=0, description="Source node index")
    target: int = Field(..., ge=0, description="Target node index")


class floyd_warshall_run_response(BaseModel):
    dist: list[list[Optional[float]]]
    successor: list[list[Optional[int]]]


class floyd_warshall_reconstruct_response(BaseModel):
    source: int
    target: int
    path: Optional[list[int]]
    weight: Optional[float]


class floyd_warshall_matrix_model(BaseModel):
    matrix: list[list[Optional[float]]] = Field(..., description="Square distance/weight matrix where None represents no direct edge")
    successor: list[list[Optional[int]]] = Field(..., description="Square successor matrix for path reconstruction")
    source: int = Field(..., ge=0, description="Source node index")
    target: int = Field(..., ge=0, description="Target node index")

    @model_validator(mode="after")
    def _validate_matrix_and_indices(self) -> "floyd_warshall_matrix_model":
        n = len(self.matrix)
        if n == 0:
            raise ValueError("Matrix cannot be empty.")
        
        for i, row in enumerate(self.matrix):
            if len(row) != n:
                raise ValueError(f"Row {i} of matrix has length {len(row)}, but matrix must be square ({n}x{n}).")
        
        if len(self.successor) != n:
            raise ValueError(f"Successor matrix size ({len(self.successor)}) must match distance matrix size ({n}).")
            
        for i, row in enumerate(self.successor):
            if len(row) != n:
                raise ValueError(f"Row {i} of successor matrix has length {len(row)}, but successor matrix must be square ({n}x{n}).")

        if self.source >= n:
            raise ValueError(f"Source index {self.source} is out of bounds for matrix of size {n}.")
            
        if self.target >= n:
            raise ValueError(f"Target index {self.target} is out of bounds for matrix of size {n}.")
            
        return self

