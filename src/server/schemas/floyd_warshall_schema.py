from pydantic import BaseModel, Field
from typing import Optional, Annotated


class node_point_model(BaseModel):
    area: float = Field(..., gt=0, description="Area of the plot in m²")
    water_height: float = Field(..., ge=0, description="Current water height in m")
    optimal_height: float = Field(..., ge=0, description="Optimal water height in m")
    elevation: float = Field(..., description="Elevation of the plot in m")


class geometry_point_model(BaseModel):
    lon: Annotated[float, Field(..., ge=-180, le=180, description="Longitude in decimal degrees")]
    lat: Annotated[float, Field(..., ge=-90, le=90, description="Latitude in decimal degrees")]


class node_edge_model(BaseModel):
    u: int = Field(..., ge=0, description="Source node index (0-indexed)")
    v: int = Field(..., ge=0, description="Destination node index (0-indexed)")
    centroid_u: geometry_point_model = Field(..., description="Geometry centroid point of the source node")
    centroid_v: geometry_point_model = Field(..., description="Geometry centroid point of the destination node")


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


class floyd_warshall_reconstruct_response(BaseModel):
    source: int
    target: int
    path: Optional[list[int]]
    distance: Optional[float]
