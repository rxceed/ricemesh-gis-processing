from server.schemas.webodm_schema import *
from server.services.webodm_service import *
from fastapi import Depends, HTTPException, status

async def webodm_project_create(ctx: webodm_project_modelBase):
    try:
        data = {"name": ctx.project_name, 
                "description": ctx.project_description
                }
        auth_token = await webodm_auth_service()
        if isinstance(auth_token, Exception):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured: {auth_token}")
        project_exists = await webodm_project_get_service(data={"name": data["name"]}, token=auth_token)
        if isinstance(project_exists, Exception):
            return {"message": "Project with that name already exists",
                    "project": project_exists}
        res = await webodm_project_create_service(data)
        if isinstance(res, Exception):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured: {res}")
        return {"message": "Project created successfully",
                "project": res}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error occured: {e}")
