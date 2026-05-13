from pymongo import AsyncMongoClient
from gridfs.asynchronous import AsyncGridFSBucket
from bson import ObjectId
from pathlib import Path

async def gridfs_upload_file(db, file_path: Path, filename: str, bucket_name:str = "fs"):
    bucket = AsyncGridFSBucket(db, chunk_size_bytes=4096*1024, bucket_name=bucket_name)
    try:
        with open(file_path, "rb") as f:
            grid_id = await bucket.upload_from_stream(filename, f)
    except Exception as e:
        return e
    return grid_id

async def gridfs_download_file(db, file_id: ObjectId, file_path: Path, bucket_name:str = "fs"):
    bucket = AsyncGridFSBucket(db, chunk_size_bytes=4096*1024, bucket_name=bucket_name)
    grid_out = await bucket.open_download_stream(file_id)
    try:
        with open(file=file_path, mode="wb") as file:
            while True:
                chunk = await grid_out.readchunk()
                if not chunk:
                    break
                file.write(chunk)
    except Exception as e:
        return e
    finally:
        await grid_out.close()
    return file_path