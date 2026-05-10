from pymongo import AsyncMongoClient
from gridfs.asynchronous import AsyncGridFSBucket
from bson import ObjectId
from pathlib import Path

async def gridfs_upload_file(db, file_data, filename: str, bucket_name:str = "fs"):
    bucket = AsyncGridFSBucket(db, chunk_size_bytes=4096*1024, bucket_name=bucket_name)
    try:
        grid_in = bucket.open_upload_stream(filename)
        await grid_in.write(file_data)
        grid_id = grid_in._id
        await grid_in.close()
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
        await grid_out.close()
    except Exception as e:
        return e
    return file_path