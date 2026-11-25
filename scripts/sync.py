#!/usr/bin/env python3
"""Preview or synchronize ONE app into a local 1Panel resource directory."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

from appstore import ROOT, SECRET, app_path, file_map, read_env, require_valid


def synchronize(app: Path, target: Path, apply: bool = False, root: Path = ROOT) -> dict:
    require_valid(app, root)
    target = Path(os.path.abspath(target.expanduser()))
    if target.parts[-3:] != ('resource', 'apps', 'local'):
        raise ValueError('--target must end in resource/apps/local; installed-instance directories are not supported')
    if any(p.is_symlink() for p in [target, *target.parents]):
        raise ValueError('target must not traverse symlinks')
    dest = target / app.name
    if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
        raise ValueError('destination must be a real directory')
    before = file_map(dest) if dest.exists() else {}
    after = file_map(app)
    if dest.exists():
        for f in dest.rglob('*'):
            if f.is_file() and (f.suffix in ('.db', '.sqlite', '.sqlite3', '.log') or f.name.endswith(('-wal', '-shm'))):
                raise ValueError('destination contains runtime data; synchronize only application resources')
            if f.is_file() and f.name == '.env':
                if any(SECRET.search(k) and v for k, v in read_env(f).items()):
                    raise ValueError('destination contains nonempty credentials; inspect before replacing resources')
    changes = {
        'added': sorted(after.keys() - before.keys()),
        'changed': sorted(k for k in after.keys() & before.keys() if after[k] != before[k]),
        'removed': sorted(before.keys() - after.keys()),
    }
    result = {'destination': str(dest), 'changes': changes, 'applied': False, 'backup': None}
    if not apply or not any(changes.values()):
        return result
    target.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.appstore-stage-', dir=target.parent))
    backup = None
    try:
        staged = staging / app.name
        shutil.copytree(app, staged)
        if dest.exists():
            backup_root = target.parent / 'local-backups'
            if backup_root.is_symlink():
                raise ValueError('backup directory must not be a symlink')
            backup_root.mkdir(exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            backup = backup_root / f'{app.name}-{stamp}-{uuid.uuid4().hex[:8]}'
            os.replace(dest, backup)
        try:
            os.replace(staged, dest)
        except OSError:
            if backup is not None:
                os.replace(backup, dest)
            raise
        result.update(applied=True, backup=str(backup) if backup else None)
    finally:
        shutil.rmtree(staging)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', help='only this application will be synchronized')
    parser.add_argument('--target', type=Path, default=Path('/opt/1panel/resource/apps/local'))
    parser.add_argument('--apply', action='store_true', help='write changes; by default only preview')
    args = parser.parse_args()
    try:
        result = synchronize(app_path(args.app), args.target, args.apply)
        print(result['destination'])
        for kind, paths in result['changes'].items():
            for path in paths:
                print(f'{kind:7} {path}')
        print('Applied.' if result['applied'] else 'No files written (preview or no changes).')
        if result['backup']:
            print('Backup:', result['backup'])
        return 0
    except (OSError, ValueError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
