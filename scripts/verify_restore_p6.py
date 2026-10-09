"""隔离恢复后，用四个应用账号执行真实 Alembic 升/降级，证明对象所有权可用。"""
from __future__ import annotations

import os
import shlex
import subprocess


def main() -> None:
    for name in ('IAM', 'AUDIT', 'POLICY', 'CODEBOOK'):
        if not os.environ[f'{name}_DB_NAME'].endswith('_p6_db'):
            raise SystemExit('仅允许 P6 隔离库')
    compose = shlex.split(os.environ['P6_COMPOSE'])
    for service in ('iam-service', 'audit-service', 'codebook-service', 'policy-service'):
        prefix = [*compose, 'exec', '-T', service]
        subprocess.run([*prefix, '.venv/bin/alembic', 'upgrade', 'head'], check=True)
        code = '''from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory
config=Config('alembic.ini')
head=ScriptDirectory.from_config(config).get_current_head()
path=Path('migrations/versions/review_restore_probe.py')
assert not path.exists()
source="from alembic import op\\nimport sqlalchemy as sa\\nrevision='review_restore_probe'\\ndown_revision="+repr(head)+"\\nbranch_labels=None\\ndepends_on=None\\ndef upgrade():\\n    op.add_column('alembic_version',sa.Column('restore_probe',sa.String(8),nullable=True))\\ndef downgrade():\\n    op.drop_column('alembic_version','restore_probe')\\n"
path.write_text(source)
'''
        subprocess.run([*prefix, '.venv/bin/python', '-c', code], check=True)
        try:
            subprocess.run([*prefix, '.venv/bin/alembic', 'upgrade', 'head'], check=True)
            subprocess.run([*prefix, '.venv/bin/alembic', 'downgrade', '-1'], check=True)
        finally:
            subprocess.run([*prefix, '.venv/bin/python', '-c', "from pathlib import Path; Path('migrations/versions/review_restore_probe.py').unlink()"], check=True)
        subprocess.run([*prefix, '.venv/bin/alembic', 'check'], check=True)
        print(service, 'restore_next_migration_ok', flush=True)
    print('RESTORE_MIGRATIONS_OK')


if __name__ == '__main__':
    main()
