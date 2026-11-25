#!/usr/bin/env python3
"""Validate all packages, or one selected application. No container startup."""

import argparse
from pathlib import Path
import sys

from appstore import ROOT, app_path, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', nargs='?', help='application key; omit to check all')
    parser.add_argument('--compose', action='store_true', help='also run docker compose config (no daemon required)')
    args = parser.parse_args()
    try:
        apps = [app_path(args.app)] if args.app else [app_path(p.name) for p in sorted((ROOT / 'apps').iterdir()) if p.is_dir()]
        if not apps:
            raise ValueError('no applications found')
        failed = False
        for app in apps:
            errors = validate(app, compose_check=args.compose)
            for error in errors:
                print(f'ERROR {app.name}: {error}', file=sys.stderr)
            if not errors:
                print(f'OK {app.name}')
            failed |= bool(errors)
        return int(failed)
    except (OSError, ValueError, TimeoutError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
