from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional

from server.schemas.processed_map_schema import processed_map_download_model
from server.services.processed_map_service import (
    processed_map_get_asset_service,
    processed_map_stream_chunks_service,
    processed_map_read_all_service,
)

async def processed_map_download(ctx: processed_map_download_model, db) -> StreamingResponse:
    """
    Downloads the full DTM or Orthophoto .tif file from MongoDB GridFS.
    """
    asset = await processed_map_get_asset_service(
        owner_id=ctx.owner_id,
        project_name=ctx.project_name,
        task_name=ctx.task_name,
        asset_type=ctx.asset_type,
    )
    if not asset:
        raise HTTPException(
            status_code=404, 
            detail=f"Asset '{ctx.asset_type}' not found for task '{ctx.task_name}' in project '{ctx.project_name}'."
        )

    # Stream chunks from GridFS
    chunks = processed_map_stream_chunks_service(db, asset.gridfs_file_id)

    filename = f"{ctx.project_name}_{ctx.task_name}_{ctx.asset_type}"
    if not filename.lower().endswith((".tif", ".tiff")):
        filename += ".tif"

    return StreamingResponse(
        chunks,
        media_type="image/tiff",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Length": str(asset.file_size_bytes)
        },
    )


async def processed_map_display(
    ctx: processed_map_download_model,
    db,
    max_dim: Optional[int] = 1024,
    quality: Optional[int] = 85
) -> StreamingResponse:
    """
    Serves a compressed JPEG preview of the Orthophoto or DTM with georeferencing headers.
    """
    import io
    from PIL import Image

    if max_dim is not None and max_dim <= 0:
        max_dim = 1024
    if quality is not None and (quality < 1 or quality > 100):
        quality = 85

    asset = await processed_map_get_asset_service(
        owner_id=ctx.owner_id,
        project_name=ctx.project_name,
        task_name=ctx.task_name,
        asset_type=ctx.asset_type,
    )
    if not asset:
        raise HTTPException(
            status_code=404, 
            detail=f"Asset '{ctx.asset_type}' not found for task '{ctx.task_name}' in project '{ctx.project_name}'."
        )

    file_bytes = await processed_map_read_all_service(db, asset.gridfs_file_id)

    try:
        image = Image.open(io.BytesIO(file_bytes))
    except Exception as img_err:
        raise HTTPException(status_code=500, detail=f"Failed to open image: {img_err}")

    w_orig, h_orig = image.width, image.height

    if max_dim and (w_orig > max_dim or h_orig > max_dim):
        if w_orig > h_orig:
            w_new = max_dim
            h_new = int(h_orig * (max_dim / w_orig))
        else:
            h_new = max_dim
            w_new = int(w_orig * (max_dim / h_orig))
        
        resample_filter = getattr(Image, "Resampling", None)
        if resample_filter is not None:
            resample_mode = resample_filter.LANCZOS
        else:
            resample_mode = getattr(Image, "ANTIALIAS", Image.BICUBIC)
            
        image = image.resize((w_new, h_new), resample_mode)

    if image.mode != "RGB":
        image = image.convert("RGB")

    jpeg_buffer = io.BytesIO()
    image.save(jpeg_buffer, format="JPEG", quality=quality)
    jpeg_buffer.seek(0)

    # Extract georeferencing headers from TIFF metadata
    geo_headers = {}
    try:
        import rasterio
        from rasterio.io import MemoryFile
        
        with MemoryFile(file_bytes) as memfile:
            with memfile.open() as src:
                bounds = src.bounds
                crs_str = src.crs.to_string() if src.crs else "unknown"
                t = src.transform
                transform_str = f"{t.a},{t.b},{t.c},{t.d},{t.e},{t.f}"
                
                geo_headers = {
                    "X-Raster-Bounds": f"{bounds.left},{bounds.bottom},{bounds.right},{bounds.top}",
                    "X-Raster-CRS": crs_str,
                    "X-Raster-Transform": transform_str
                }
    except Exception as geo_err:
        print(f"Warning: Failed to extract georeferencing headers: {geo_err}")

    return StreamingResponse(
        jpeg_buffer,
        media_type="image/jpeg",
        headers=geo_headers,
    )
