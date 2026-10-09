"""经隔离网关验证上传资源限制；不得指向业务库。"""
import os
from io import BytesIO

import httpx
from openpyxl import Workbook

from accept import Api

for service in ('IAM', 'AUDIT', 'POLICY', 'CODEBOOK'):
    assert os.environ[f'{service}_DB_NAME'].endswith('_p6_db'), '拒绝业务库'
base = os.environ['P6_GATEWAY']
api = Api(base)
api.login(os.environ['ADMIN_USERNAME'], os.environ['ADMIN_PASSWORD'])
headers = {'Authorization': 'Bearer '+api.token}
book = Workbook()
book.active.append(['省份名称']+['字段']*128)
book.active.append(['广东省'])
buf = BytesIO()
book.save(buf)
with httpx.Client(base_url=base, timeout=30, trust_env=False) as client:
    response=client.post('/api/v1/codebook/area-codes/resolve',headers=headers,files={'file':('wide.xlsx',buf.getvalue())})
    assert response.status_code==422 and '列数' in response.json()['message'], response.text
    response=client.post('/api/v1/policy/sources/import',headers={'Authorization':'Bearer invalid'},files={'file':('test.xlsx',b'abc')})
    assert response.status_code==401,response.text
    def chunks():
        yield b'--x\r\nContent-Disposition: form-data; name="file"; filename="big.xlsx"\r\n\r\n'
        for _ in range(22): yield b'x'*(1024*1024)
        yield b'\r\n--x--\r\n'
    response=client.post('/api/v1/policy/sources/import',headers={**headers,'Content-Type':'multipart/form-data; boundary=x'},content=chunks())
    assert response.status_code==413,response.text
print('upload_gateway_auth_and_limits_ok')
