"""隔离恢复后，用各服务的应用账号执行真实 Alembic 升/降级，证明对象所有权可用。"""
from __future__ import annotations

import os
import shlex
import subprocess
import tarfile
from pathlib import Path

# 备份目录里的附件包 -> 解到哪个容器的哪个目录（和 restore.sh 一致）
FILE_ARCHIVES = (
    ("ai-files.tar.gz", "ai-service", "/data/ai"),
    ("thinktank-files.tar.gz", "thinktank-service", "/data/thinktank"),
)


def verify_files(compose: list[str], backup: Path) -> None:
    """附件包里的每个文件恢复后都要在卷里：库回到了备份点、附件没回去，页面上就是一堆打不开的文件。"""

    for name, service, root in FILE_ARCHIVES:
        archive = backup / name
        if not archive.is_file():
            continue
        with tarfile.open(archive) as tar:
            files = [member.name for member in tar.getmembers() if member.isfile()]
        script = 'cd "$1" && while IFS= read -r f; do [ -f "$f" ] || echo "$f"; done'
        missing = subprocess.run(
            [*compose, "exec", "-T", service, "sh", "-c", script, "sh", root],
            input="".join(f"{path}\n" for path in files),
            text=True,
            capture_output=True,
            check=True,
        ).stdout.splitlines()
        if missing:
            raise SystemExit(f"{name} 恢复后 {service}:{root} 缺 {len(missing)} 个文件，如 {missing[:3]}")
        print(name, "restore_files_ok", len(files), flush=True)


def main() -> None:
    for name in ('IAM', 'AUDIT', 'POLICY', 'CODEBOOK', 'AI', 'THINKTANK'):
        if not os.environ[f'{name}_DB_NAME'].endswith('_p6_db'):
            raise SystemExit('仅允许 P6 隔离库')
    compose = shlex.split(os.environ['P6_COMPOSE'])
    for service in ('iam-service', 'audit-service', 'codebook-service', 'policy-service', 'ai-service', 'thinktank-service'):
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
    backup = os.environ.get("RESTORE_BACKUP", "")
    if backup:
        verify_files(compose, Path(backup))


if __name__ == '__main__':
    main()
