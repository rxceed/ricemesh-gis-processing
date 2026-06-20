from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from typing import Optional

from server.schemas.processed_map_schema import processed_map_download_model as _processed_map_download_model
from server.controllers.processed_map_controller import (
    processed_map_download as _processed_map_download,
    processed_map_display as _processed_map_display,
)

processed_map_router = APIRouter(prefix="/processed-map", tags=["Processed Map"])

@processed_map_router.get("/download")
async def download_asset(
    req: Request,
    ctx: _processed_map_download_model = Depends(),
):
    """
    Download a processed map asset (orthophoto or dtm) from MongoDB GridFS.
    """
    return await _processed_map_download(ctx, req.app.state.db)


@processed_map_router.get("/display")
async def display_asset(
    req: Request,
    ctx: _processed_map_download_model = Depends(),
    max_dim: Optional[int] = 1024,
    quality: Optional[int] = 85,
):
    """
    Display a compressed JPEG preview of a processed map asset from MongoDB GridFS.
    """
    return await _processed_map_display(ctx, req.app.state.db, max_dim=max_dim, quality=quality)
