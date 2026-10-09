import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd()/'scripts'))
import export_openapi
export_openapi._prepare_env()
sys.path.insert(0,str(Path.cwd()/'services/policy-service'))
from app.main import app
from app.core.database import get_db_session
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile
from platform_common.errors import UnauthenticatedError
route=next(r for r in app.routes if getattr(r,'path',None)=='/api/v1/policy/interpretations/import')
state={'parsed_bytes':0,'parsed_before_auth':0}
async def db(): yield None
async def deny():
 state['parsed_before_auth']=state['parsed_bytes']
 raise UnauthenticatedError()
app.dependency_overrides[get_db_session]=db
for dep in route.dependant.dependencies:
 if dep.name=='actor':app.dependency_overrides[dep.call]=deny
original=UploadFile.write
async def counted(self,data):
 state['parsed_bytes']+=len(data)
 return await original(self,data)
with patch.object(UploadFile,'write',counted):
 response=TestClient(app).post(route.path,files={'file':('oversize.xlsx',b'x'*(21*1024*1024),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
print('UPLOAD_REPRO',{'status':response.status_code,**state})
