from bson import ObjectId
from gridfs.asynchronous import AsyncGridFSBucket
from db.models import WebODMAsset

async def processed_map_get_asset_service(
    owner_id: str,
    project_name: str,
    task_name: str,
    asset_type: str,
) -> WebODMAsset:
    """
    Finds a WebODMAsset by owner_id, project_name, task_name, and asset_type.
    """
    clean_type = asset_type.lower().replace(".tif", "").replace(".tiff", "")
    asset = await WebODMAsset.find_one({
        "ownerId": owner_id,
        "projectName": project_name,
        "taskName": task_name,
        "assetType": clean_type
    })
    return asset


async def processed_map_stream_chunks_service(db, file_id: ObjectId):
    """
    Generator that streams a file from GridFS chunk by chunk.
    """
    bucket = AsyncGridFSBucket(db, chunk_size_bytes=4096*1024, bucket_name="webodm_assets")
    grid_out = await bucket.open_download_stream(file_id)
    try:
        while True:
            chunk = await grid_out.readchunk()
            if not chunk:
                break
            yield chunk
    finally:
        await grid_out.close()


async def processed_map_read_all_service(db, file_id: ObjectId) -> bytes:
    """
    Reads the entire file content from GridFS into memory.
    """
    bucket = AsyncGridFSBucket(db, bucket_name="webodm_assets")
    grid_out = await bucket.open_download_stream(file_id)
    try:
        content = await grid_out.read()
        return content
    finally:
        await grid_out.close()
