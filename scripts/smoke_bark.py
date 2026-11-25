#!/usr/bin/env python3
"""Test Bark in temporary Docker projects; never use production device tokens."""

import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from appstore import ROOT, app_path, require_valid, selected_version


def run(args, *, check=True, timeout=90):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(' '.join(args[:3]) + ' failed: ' + p.stderr[-2000:])
    return p


def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='2.4.0')
    parser.add_argument('--mysql', action='store_true', help='also test with an isolated official mysql:8.4 container')
    parser.add_argument('--output', type=Path, default=ROOT / 'work/docker-bark.json')
    args = parser.parse_args()
    app = app_path('bark')
    require_valid(app)
    source = selected_version(app, args.version)
    work = ROOT / 'work'
    work.mkdir(exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix='bark-smoke-', dir=work)
    folder = Path(temporary.name)
    token = secrets.token_hex(5)
    network = 'bark-smoke-' + token
    mysql_name = network + '-db'
    projects = []
    checks = []
    network_created = False
    mysql_created = False
    result = {'date': datetime.now(timezone.utc).isoformat(), 'version': args.version,
              'checks': checks, 'limitations': ['No real APNs delivery', 'No actual 1Panel install/upgrade'],
              'test_overrides': 'Loopback-only ports; dedicated external network name; temporary instance names and credentials.'}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def passed(name):
        checks.append(name)
        print('PASS:', name, flush=True)

    def compose(p, *arguments, check=True):
        return run(['docker', 'compose', '-p', p['name'], '--project-directory', str(p['dir']),
                    '-f', str(p['dir'] / 'docker-compose.yml'), '-f', str(p['dir'] / 'test.yml'), *arguments], check=check)

    def request(p, path, data=None, auth=None):
        headers = {}
        if auth:
            headers['Authorization'] = 'Basic ' + base64.b64encode(':'.join(auth).encode()).decode()
        if data is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(data).encode()
        req = urllib.request.Request(f'http://127.0.0.1:{p["port"]}{path}', data=data, headers=headers)
        try:
            with opener.open(req, timeout=3) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def ready(p):
        for _ in range(80):
            try:
                code, body = request(p, '/ping')
                if code == 200 and json.loads(body)['message'] == 'pong':
                    return
            except (OSError, ValueError):
                pass
            time.sleep(0.25)
        raise RuntimeError('Bark did not become ready: ' + compose(p, 'logs', '--no-color', check=False).stdout[-2000:])

    def create(name, auth=('', ''), dsn=''):
        p = {'name': network + '-' + name, 'dir': folder / name, 'port': port()}
        shutil.copytree(source, p['dir'])
        values = {'CONTAINER_NAME': p['name'], 'PANEL_APP_PORT_HTTP': str(p['port']),
                  'BARK_SERVER_BASIC_AUTH_USER': auth[0], 'BARK_SERVER_BASIC_AUTH_PASSWORD': auth[1], 'BARK_SERVER_DSN': dsn}
        (p['dir'] / '.env').write_text(''.join(f"{key}='{value}'\n" for key, value in values.items()))
        (p['dir'] / 'test.yml').write_text('services:\n  bark:\n    ports: !override\n      - "127.0.0.1:${PANEL_APP_PORT_HTTP}:8080"\n'
                                        f'networks:\n  1panel-network:\n    name: {network}\n')
        projects.append(p)
        compose(p, 'config', '--quiet')
        compose(p, 'up', '-d')
        ready(p)
        return p

    def register(p):
        code, body = request(p, '/register', {'device_token': '0' * 64})
        assert code == 200, body
        key = json.loads(body)['data']['device_key']
        assert request(p, '/register/' + key)[0] == 200
        return key

    try:
        info = json.loads(run(['docker', 'info', '--format', '{{json .}}']).stdout)
        result['docker'] = {'version': info['ServerVersion'], 'architecture': info['Architecture']}
        run(['docker', 'network', 'create', '--label', 'appstore.smoke=' + token, network])
        network_created = True
        p = create('default')
        assert request(p, '/healthz') == (200, 'ok')
        assert request(p, '/') == (200, 'ok')
        actual = json.loads(request(p, '/info')[1])
        assert actual['version'] == 'v' + args.version, actual
        result['image_info'] = actual
        passed('Packaged Compose starts; ping, healthz, root and actual image version match')
        key = register(p)
        assert (p['dir'] / 'data/bark.db').stat().st_size > 0
        passed('Device registration writes to relative Bbolt mount')
        compose(p, 'restart')
        ready(p)
        assert request(p, '/register/' + key)[0] == 200
        passed('Registration survives restart')
        compose(p, 'down')
        compose(p, 'up', '-d')
        ready(p)
        assert request(p, '/register/' + key)[0] == 200
        passed('Registration survives removal and recreation')
        compose(p, 'stop')
        compose(p, 'start')
        ready(p)
        assert request(p, '/register/' + key)[0] == 200
        passed('Stop/start preserves data')
        auth = ('smoke', 'test$literal#' + token)
        q = create('auth', auth)
        assert request(q, '/info')[0] == 418
        assert request(q, '/info', auth=('wrong', 'wrong'))[0] == 418
        assert request(q, '/info', auth=auth)[0] == 200
        fake_push = {'device_key': 'nonexistent', 'body': 'local smoke test'}
        assert request(q, '/push', fake_push)[0] == 418
        assert request(q, '/push', fake_push, auth)[0] == 400
        assert request(q, '/healthz') == (200, 'ok')
        register(q)
        passed('Basic Auth, special-character password, upstream public endpoints and push rejection')
        assert request(q, '/register/' + key)[0] == 400
        assert request(p, '/register/' + key)[0] == 200
        passed('Concurrent instances have independent databases')
        compose(p, 'stop')
        migrated = create('migrated')
        compose(migrated, 'stop')
        shutil.copytree(p['dir'] / 'data', migrated['dir'] / 'data', dirs_exist_ok=True)
        compose(migrated, 'start')
        ready(migrated)
        assert request(migrated, '/register/' + key)[0] == 200
        passed('Offline database migration to a new installation directory')
        if args.mysql:
            print('Testing optional external MySQL...', flush=True)
            run(['docker', 'pull', 'mysql:8.4'], timeout=240)
            run(['docker', 'run', '-d', '--name', mysql_name, '--network', network,
                 '--label', 'appstore.smoke=' + token, '--tmpfs', '/var/lib/mysql',
                 '-e', 'MYSQL_ROOT_PASSWORD=test-' + token, '-e', 'MYSQL_DATABASE=bark',
                 '-e', 'MYSQL_USER=bark', '-e', 'MYSQL_PASSWORD=test-' + token, 'mysql:8.4'])
            mysql_created = True
            for _ in range(120):
                status = run(['docker', 'exec', mysql_name, 'mysql', '-ubark', '-ptest-' + token, 'bark', '-e', 'SELECT 1'], check=False)
                if not status.returncode:
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError('MySQL did not become ready')
            m = create('mysql', dsn=f'bark:test-{token}@tcp({mysql_name}:3306)/bark')
            mk = register(m)
            rows = run(['docker', 'exec', mysql_name, 'mysql', '-ubark', '-ptest-' + token, 'bark', '-N', '-e', 'SELECT COUNT(*) FROM devices'])
            assert rows.stdout.strip() == '1'
            compose(m, 'down')
            compose(m, 'up', '-d')
            ready(m)
            assert request(m, '/register/' + mk)[0] == 200
            passed('External MySQL schema, registration, actual row and app recreation')
        result['status'] = 'passed'
    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)
        print('FAIL:', e, flush=True)
    finally:
        cleanup = []
        for p in reversed(projects):
            cleanup.append(compose(p, 'down', '--remove-orphans', check=False).returncode == 0)
        if mysql_created:
            cleanup.append(run(['docker', 'rm', '-f', '-v', mysql_name], check=False).returncode == 0)
        if network_created:
            cleanup.append(run(['docker', 'network', 'rm', network], check=False).returncode == 0)
        result['cleanup_passed'] = all(cleanup)
        if not result['cleanup_passed']:
            result['status'] = 'failed'
            result['error'] = 'Docker cleanup failed; inspect resources with prefix ' + network
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        temporary.cleanup()
    print('Result:', result['status'], flush=True)
    return int(result['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())
