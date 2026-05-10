import requests
from dotenv import load_dotenv
import os

load_dotenv()

WEBODM_ROOT = os.getenv("WEBODM_ROOT")
WEBDOM_USER = os.getenv("WEBODM_USER")
WEBODM_PASS = os.getenv("WEBODM_PASS")

async def webodm_auth_service(data: dict):
    """
    Args:
        data: dict{username: str, password: str}
    Returns:
        token: str
    """
    try:
        auth_api_path = WEBODM_ROOT+"/api/token-auth/"
        data = {"username": WEBDOM_USER, "password": WEBODM_PASS}
        res = requests.post(auth_api_path, data=data)
        res.raise_for_status()
        return res.json()["token"]
    except Exception as e:
        return e
    
async def webodm_project_get_service(data: dict, token: str):
    """
    Args:
        data: filters = dict{name: str}
    """
    try:
        project_api_path = WEBODM_ROOT+"/api/projects/"
        res = requests.get(project_api_path, data=data, headers={"Authorization": f"JWT {token}"})
        res.raise_for_status()
        return res.json()
    except Exception as e:
        return e

async def webodm_project_create_service(data: dict, token: str):
    """
    Args:
        data: dict{name: str,
                    description: str}
    """
    try:
        project_api_path = WEBODM_ROOT+"/api/projects/"
        res = requests.post(project_api_path, data=data, headers={"Authorization": f"JWT {token}"})
        res.raise_for_status()
        return res.json()
    except Exception as e:
        return e

async def webodm_task_create_service(data: dict, token: str):
    """
    Args:
        data: dict{project_name: str}
        token: str
    """
    try:
        task_api_path = WEBODM_ROOT+"/api/tasks/"
    except Exception as e:
        return e