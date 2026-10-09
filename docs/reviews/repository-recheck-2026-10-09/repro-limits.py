import sys, asyncio, io
from pathlib import Path
from unittest.mock import patch
root=Path('/Users/liuxingping/Desktop/developer/project/tx-zhongtai')
sys.path[:0]=[str(root/'packages/platform-common'), str(root/'services/codebook-service')]
from openpyxl import Workbook
from platform_common.columns import ColumnSpec
from platform_common.excel import parse_sheet
from platform_common.http_utils import read_import_upload
from platform_common.errors import ApiError
from app.application.area_resolve import read_raw_sheet
from starlette.datastructures import Headers
import starlette.formparsers as fp

def excel(build):
    w=Workbook(); build(w.active); b=io.BytesIO(); w.save(b); return b.getvalue()
b=excel(lambda s: (s.append(['省份名称'] + ['extra']*128),s.append(['广东省'])))
h,r=read_raw_sheet(b)
print('area_resolve_129_columns_accepted',len(h))
b=excel(lambda s: (s.append(['网站名称']),setattr(s.cell(100003,1),'value','最后一行')))
r=parse_sheet(b,(ColumnSpec('site_name','网站名称'),))
print('common_sparse_row_100003_accepted',len(r))
async def probe():
    files=[]; real=fp.SpooledTemporaryFile
    def capture(*a,**kw):
        f=real(*a,**kw);files.append(f); return f
    class R:
        headers=Headers({'content-type':'multipart/form-data; boundary=x'})
        async def stream(self):
            yield b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.xlsx"\r\n\r\n'+b'a'*(1100*1024)
            yield b'a'*(300*1024)
    with patch.object(fp,'SpooledTemporaryFile',capture):
        try: await read_import_upload(R(),1024*1024)
        except ApiError as e: print('over_limit_status',e.http_status)
    print('temporary_files_closed_after_rejection',[f.closed for f in files])
    for f in files: f.close()
asyncio.run(probe())
