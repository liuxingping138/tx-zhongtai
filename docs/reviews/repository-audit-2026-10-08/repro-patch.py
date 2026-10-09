import sys,asyncio,uuid
from pathlib import Path
from unittest.mock import AsyncMock,patch
from datetime import datetime,UTC
sys.path.insert(0,str(Path.cwd()/'scripts'))
import export_openapi
export_openapi._prepare_env()
sys.path.insert(0,str(Path.cwd()/'services/codebook-service'))
from app.api.schemas import ScenarioWrite
from app.application import scenarios
from app.domain.models import Scenario,SCENARIO_FIELDS
from platform_common.actors import Actor
async def run():
 now=datetime.now(UTC)
 original={f:'original-'+f for f in SCENARIO_FIELDS}
 row=Scenario(id=uuid.uuid4(),content_hash='x',version=1,created_at=now,updated_at=now,created_by_name='tester',updated_by_name='tester',**original)
 body=ScenarioWrite(version=1,scenario_tag='changed')
 with patch.object(scenarios.repo,'get_for_update',AsyncMock(return_value=row)),patch.object(scenarios.repo,'get_by_hash',AsyncMock(return_value=None)),patch.object(scenarios,'enqueue_event',AsyncMock()):
  await scenarios.update_scenario(AsyncMock(),Actor(id='review',name='review'),row.id,body.model_dump())
 print('PATCH_REPRO',{'submitted':sorted(body.model_fields_set),'cleared_unsubmitted_fields':[f for f in SCENARIO_FIELDS if f not in body.model_fields_set and getattr(row,f)=='']})
asyncio.run(run())
