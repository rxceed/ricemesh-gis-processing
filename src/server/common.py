from dotenv import load_dotenv as _load_dotenv
import os as _os
from db.connection import connect_client, connect_db

_load_dotenv()

_MONGO_BASE_URI = _os.getenv("MONGO_BASE_ADDRESS")
_MONGO_USER = _os.getenv("MONGO_ROOT_USER")
_MONGO_PW = _os.getenv("MONGO_ROOT_PASS")

MONGO_URI = f"mongodb://{_MONGO_USER}:{_MONGO_PW}@{_MONGO_BASE_URI}"

