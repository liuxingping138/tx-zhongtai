"""仅在 P6 隔离四库验证真实 HTTP PATCH、持久化与乐观锁。"""
import os
import uuid

from accept import Api, expect


def run() -> None:
    for service in ('IAM', 'AUDIT', 'POLICY', 'CODEBOOK'):
        assert os.environ[f'{service}_DB_NAME'].endswith('_p6_db'), '拒绝业务库'
    api = Api(os.environ['P6_GATEWAY'])
    api.login(os.environ['ADMIN_USERNAME'], os.environ['ADMIN_PASSWORD'])
    def read_row(path, detail, route, item_id):
        if route == 'codebook/policy-types':
            code, result = api.call('GET', path+'?page_size=100')
            expect(code == 200, f'{route} list {code}')
            return 200, {'data': next(x for x in result['data']['items'] if x['id'] == item_id)}
        return api.call('GET', detail)

    suffix = uuid.uuid4().hex[:10]
    cases = [
        ('policy/sources', {'site_name': '验收'+suffix, 'province_code': '440000', 'department': '保留字段'}, 'url'),
        ('policy/base-tags', {'policy_name': '验收'+suffix, 'issuing_dept': '保留字段'}, 'remark'),
        ('policy/interpretations', {'policy_title': '验收'+suffix, 'target_customers': '保留字段'}, 'policy_summary'),
        ('codebook/policy-types', {'type_name': '验收'+suffix, 'seq_no': '123'}, 'definition'),
        ('codebook/scenarios', {'scenario_tag': '验收'+suffix, 'industry_l1': '保留字段'}, 'desc_90'),
        ('codebook/area-codes', {'county_id': suffix, 'prov_name': '保留字段'}, 'alias_city_name'),
    ]
    for route, payload, field in cases:
        path='/api/v1/'+route
        code, body=api.call('POST',path,payload)
        expect(code==201, f'{route} create {code} {body}')
        row=body['data']; detail=path+'/'+row['id']
        code, body=api.call('PATCH',detail,{'version':row['version'],field:'修改内容'})
        expect(code==200,f'{route} patch {code} {body}')
        code, body=read_row(path,detail,route,row['id'])
        expect(code==200,f'{route} get {code}')
        after=body['data']
        for key in payload:
            expect(after[key]==row[key],f'{route} omitted {key} lost')
        expect(after[field]=='修改内容',f'{route} change not persisted')
        code,_=api.call('PATCH',detail,{'version':row['version'],field:'过期版本'})
        expect(code==409,f'{route} stale version {code}')
        code,_=api.call('PATCH',detail,{'version':after['version'],field:''})
        expect(code==200,f'{route} clear {code}')
        code,body=read_row(path,detail,route,row['id'])
        expect(body['data'][field]=='',f'{route} clear not persisted')
        required = {'policy/sources':'site_name', 'policy/base-tags':'policy_name',
                    'policy/interpretations':'policy_title', 'codebook/policy-types':'type_name'}.get(route)
        if required:
            code,_=api.call('PATCH',detail,{'version':body['data']['version'],required:''})
            expect(code==422,f'{route} blank required field {code}')
        print(route,'partial_update_persisted_and_conflict_ok')
    print('business_patch_ok')


if __name__=='__main__':
    run()
