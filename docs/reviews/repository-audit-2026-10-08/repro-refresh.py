import sys,asyncio,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from datetime import datetime,UTC,timedelta
sys.path.insert(0,str(Path.cwd()/'scripts'))
import export_openapi
export_openapi._prepare_env()
sys.path.insert(0,str(Path.cwd()/'services/iam-service'))
from app.application.auth_service import AuthService
from app.core.config import Settings
from app.core import database
from platform_common.errors import UnauthenticatedError
async def replay():
 now=datetime.now(UTC)
 token=SimpleNamespace(session_id=uuid.uuid4(),consumed_at=now-timedelta(seconds=60),replaced_by=uuid.uuid4())
 sess=SimpleNamespace(family_id=uuid.uuid4(),user_id=uuid.uuid4(),id=token.session_id)
 db=AsyncMock();factory=AsyncMock();factory.__aenter__.return_value=db
 with patch.object(database,'SessionLocal',return_value=factory),patch('app.application.auth_service.session_repo.get_refresh_token_for_update',AsyncMock(return_value=token)),patch('app.application.auth_service.session_repo.get_session',AsyncMock(return_value=sess)),patch('app.application.auth_service.session_repo.revoke_family',AsyncMock()) as revoke,patch('app.application.auth_service.outbox_repo.enqueue',AsyncMock()) as enqueue:
  dependency=database.get_db_session();session=await anext(dependency)
  try:await AuthService(session,Settings()).refresh('dummy')
  except UnauthenticatedError as e:
   try:await dependency.athrow(e)
   except UnauthenticatedError:pass
  print('REPLAY_TXN',dict(revoke_called=revoke.await_count,audit_enqueued=enqueue.await_count,commits=db.commit.await_count,rollbacks=db.rollback.await_count))
asyncio.run(replay())
