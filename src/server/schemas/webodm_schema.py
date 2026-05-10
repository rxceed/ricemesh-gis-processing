from pydantic import BaseModel

class webodm_auth_model(BaseModel):
    username: str
    password: str

class webodm_project_modelBase(BaseModel):
    project_name: str
    project_description: str | None = None