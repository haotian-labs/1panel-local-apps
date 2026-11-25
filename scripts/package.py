#!/usr/bin/env python3
"""Build a deterministic, single-version application ZIP and SHA256 file."""

import argparse
from pathlib import Path
import sys
import zipfile

from appstore import ROOT, app_path, digest, release_tag, require_valid, select_tag, selected_version


def build(app: Path, version: Path, output: Path, root: Path = ROOT) -> Path:
    require_valid(app, root)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (release_tag(app, version.name, root) + '.zip')
    files = [p for p in app.iterdir() if p.is_file()] + [p for p in version.rglob('*') if p.is_file()]
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(files):
            info = zipfile.ZipInfo(f'{app.name}/{path.relative_to(app).as_posix()}', (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if path.suffix == '.sh' else 0o100644) << 16
            z.writestr(info, path.read_bytes())
    archive.with_suffix('.zip.sha256').write_text(f'{digest(archive)}  {archive.name}\n')
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', nargs='?')
    parser.add_argument('--version')
    parser.add_argument('--tag', help='resolve an exact app-version-rN release tag from the spec')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    try:
        if args.tag:
            if args.app or args.version:
                parser.error('--tag cannot be combined with app/--version')
            app, version = select_tag(args.tag)
        else:
            if not args.app or not args.version:
                parser.error('provide app and --version, or --tag')
            app = app_path(args.app)
            version = selected_version(app, args.version)
        print(build(app, version, args.output.resolve()))
        return 0
    except (OSError, ValueError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
