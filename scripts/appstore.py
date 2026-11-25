"""Shared package validation and selection; never executes application containers."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = {'en', 'es-es', 'ja', 'ms', 'pt-br', 'ru', 'ko', 'zh-Hant', 'zh', 'tr'}
KEY = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
VERSION = re.compile(r'^[0-9][A-Za-z0-9._+-]*$')
VARIABLE = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(?:[^}]*)\}')
BUILTINS = {'CONTAINER_NAME', 'HOST_IP', 'HOST_ADDRESS'}
SECRET = re.compile(r'(?:PASSWORD|SECRET|TOKEN|API_KEY|DSN)$')


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f'duplicate YAML key: {key}')
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_yaml(path: Path) -> dict:
    value = yaml.load(path.read_text(encoding='utf-8'), Loader=UniqueLoader)
    if not isinstance(value, dict):
        raise ValueError(f'{path.name} must contain a mapping')
    return value


def app_path(key: str, root: Path = ROOT) -> Path:
    if not KEY.fullmatch(key):
        raise ValueError('invalid application key')
    path = root / 'apps' / key
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f'application does not exist or is a symlink: {key}')
    return path


def versions(app: Path) -> list[Path]:
    return sorted(p for p in app.iterdir() if p.is_dir() and not p.is_symlink() and VERSION.fullmatch(p.name))


def selected_version(app: Path, version: str) -> Path:
    if not VERSION.fullmatch(version) or (app / version) not in versions(app):
        raise ValueError(f'invalid or missing version: {version}')
    return app / version


def spec_for(app: Path, version: str, root: Path = ROOT) -> dict:
    spec = json.loads((root / 'specs' / app.name / f'{version}.json').read_text())
    if spec.get('key') != app.name or spec.get('version') != version:
        raise ValueError('spec key/version does not match package')
    revision = spec.get('package_revision')
    if type(revision) is not int or revision < 1:
        raise ValueError('package_revision must be a positive integer')
    if not spec.get('source_evidence'):
        raise ValueError('spec is missing official installation source_evidence')
    return spec


def release_tag(app: Path, version: str, root: Path = ROOT) -> str:
    return f'{app.name}-{version}-r{spec_for(app, version, root)["package_revision"]}'


def select_tag(tag: str, root: Path = ROOT) -> tuple[Path, Path]:
    for app in sorted((root / 'apps').iterdir()):
        if not app.is_dir() or app.is_symlink():
            continue
        for version in versions(app):
            if release_tag(app, version.name, root) == tag:
                return app, version
    raise ValueError('tag does not match any current app/version/package_revision')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_map(path: Path) -> dict[str, str]:
    result = {}
    for p in sorted(path.rglob('*')):
        if p.is_symlink():
            raise ValueError(f'symlinks are not allowed: {p}')
        if p.is_file():
            result[p.relative_to(path).as_posix()] = digest(p)
    return result


def locale_errors(value, label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f'{label}: multilingual mapping required']
    missing = sorted(lang for lang in LANGUAGES if not isinstance(value.get(lang), str) or not value[lang].strip())
    return [f'{label}: missing languages {", ".join(missing)}'] if missing else []


def read_env(path: Path) -> dict[str, str]:
    result = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) or key in result:
            raise ValueError(f'invalid or duplicate .env entry at line {number}')
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f'unclosed .env quote at line {number}')
            value = value[1:-1]
        result[key] = value
    return result


def validate(app: Path, compose_check: bool = False, root: Path = ROOT) -> list[str]:
    errors = []
    try:
        for name in ('data.yml', 'README.md', 'README_en.md', 'logo.png'):
            if not (app / name).is_file():
                errors.append(f'missing {name}')
        all_files = file_map(app)
        for name in all_files:
            if '.DS_Store' in name or re.search(r'\.(?:db|sqlite|log|bak)(?:$|[.-])', name):
                errors.append(f'runtime/unwanted file in package: {name}')
        meta = load_yaml(app / 'data.yml').get('additionalProperties', {})
        for key in ('key', 'name', 'tags', 'type', 'crossVersionUpdate', 'limit', 'architectures', 'website', 'github', 'document'):
            if key not in meta:
                errors.append(f'root metadata missing {key}')
        if meta.get('key') != app.name:
            errors.append('metadata key must match directory name')
        if meta.get('type') not in ('website', 'runtime', 'tool'):
            errors.append('invalid app type')
        if not isinstance(meta.get('architectures'), list) or not meta.get('architectures'):
            errors.append('architectures must be a nonempty list verified against the image')
        errors += locale_errors(meta.get('description'), 'description')
        for name, heading in [('README.md', '## 产品介绍'), ('README_en.md', '## Introduction')]:
            if heading not in (app / name).read_text():
                errors.append(f'{name} missing {heading}')
        logo = (app / 'logo.png').read_bytes()
        if len(logo) < 24 or logo[:8] != b'\x89PNG\r\n\x1a\n':
            errors.append('logo.png is not a PNG')
        elif struct.unpack('>II', logo[16:24]) != (180, 180) or len(logo) > 10240:
            errors.append('repository logo policy: PNG 180x180, at most 10 KiB')
        found = versions(app)
        if not found:
            errors.append('no version directories')
        for child in app.iterdir():
            if child.is_dir() and child not in found:
                errors.append(f'invalid version directory: {child.name}')
        for version in found:
            errors += [f'{version.name}: {e}' for e in validate_version(app, version, compose_check, root)]
    except (OSError, ValueError, KeyError, TypeError, AttributeError, yaml.YAMLError, subprocess.SubprocessError) as e:
        errors.append(f'cannot validate package: {e}')
    return errors


def validate_version(app: Path, version: Path, compose_check: bool, root: Path) -> list[str]:
    errors = []
    spec = spec_for(app, version.name, root)
    fields = load_yaml(version / 'data.yml').get('additionalProperties', {}).get('formFields')
    if not isinstance(fields, list):
        raise ValueError('additionalProperties.formFields must be a list')
    declared = {}
    for field in fields:
        key = field.get('envKey')
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) or key in declared:
            errors.append('invalid or duplicate form envKey')
            continue
        declared[key] = field
        errors += locale_errors(field.get('label'), key)
        if key.startswith('PANEL_APP_PORT_') and (field.get('type') != 'number' or field.get('rule') != 'paramPort'):
            errors.append(f'{key} must be number with paramPort')
        if SECRET.search(key):
            if field.get('type') != 'password':
                errors.append(f'{key} must use type: password')
            if field.get('default') not in ('', None):
                errors.append(f'{key} must have an empty default')
    defaults = read_env(version / '.env') if (version / '.env').exists() else {}
    for key, value in defaults.items():
        if key not in declared:
            errors.append(f'.env contains undeclared key: {key}')
        if SECRET.search(key) and value:
            errors.append(f'.env contains a nonempty secret: {key}')
        if key in declared and str(declared[key].get('default', '')) != value:
            errors.append(f'.env default differs from form default: {key}')
    compose_path = version / 'docker-compose.yml'
    content = compose_path.read_text()
    allowed = BUILTINS | set(declared)
    if {'PANEL_DB_HOST', 'PANEL_DB_TYPE'} & set(declared):
        allowed.add('PANEL_DB_PORT')
    for key in sorted(set(VARIABLE.findall(content)) - allowed):
        errors.append(f'undeclared Compose variable: {key}')
    compose = load_yaml(compose_path)
    if compose.get('networks', {}).get('1panel-network', {}).get('external') is not True:
        errors.append('1panel-network must be external: true')
    services = compose.get('services')
    if not isinstance(services, dict) or not services:
        raise ValueError('Compose services must be a nonempty mapping')
    if sum(s.get('container_name') == '${CONTAINER_NAME}' for s in services.values()) != 1:
        errors.append('exactly one primary service must use ${CONTAINER_NAME}')
    expected_images = {s['name']: s['image'] for s in spec['services']}
    for name, service in services.items():
        prefix = f'service {name}: '
        if service.get('container_name') not in ('${CONTAINER_NAME}', '${CONTAINER_NAME}-' + name):
            errors.append(prefix + 'container_name must use the panel variable')
        if service.get('image') != expected_images.get(name):
            errors.append(prefix + 'image differs from the reviewed spec')
        image = service.get('image', '')
        if not re.search(r':(?!latest$)[^/:]+$', image) and '@sha256:' not in image:
            errors.append(prefix + 'image must use a fixed tag or digest')
        if service.get('restart') != 'always' or '1panel-network' not in (service.get('networks') or []):
            errors.append(prefix + 'restart: always and 1panel-network required')
        if service.get('labels', {}).get('createdBy') != 'Apps':
            errors.append(prefix + 'createdBy: Apps required')
        if service.get('privileged') or service.get('network_mode') == 'host' or service.get('pid') == 'host':
            errors.append(prefix + 'host namespaces/privileged mode require a separately reviewed policy change')
        for port in service.get('ports', []):
            published = str(port.get('published', '')) if isinstance(port, dict) else str(port).rsplit(':', 1)[0]
            if not re.search(r'\$\{PANEL_APP_PORT_[A-Z0-9_]+\}', published):
                errors.append(prefix + 'published port must use PANEL_APP_PORT_*')
        for volume in service.get('volumes', []):
            source = volume.get('source', '') if isinstance(volume, dict) else volume.split(':', 1)[0]
            if not source.startswith('./') or '..' in Path(source).parts or '$' in source:
                errors.append(prefix + 'persistence sources must be literal relative paths')
                continue
            target = version / source
            if not target.exists():
                errors.append(prefix + 'missing mount source: ' + source)
            if target.is_dir() and sorted(p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()) != ['.gitkeep']:
                errors.append(prefix + 'persistent directory may only contain .gitkeep: ' + source)
        env_files = service.get('env_file', [])
        for entry in env_files if isinstance(env_files, list) else [env_files]:
            source = entry.get('path', '') if isinstance(entry, dict) else entry
            if Path(source).is_absolute() or '..' in Path(source).parts or not (version / source).is_file():
                errors.append(prefix + 'invalid env_file path')
    if set(services) != set(expected_images):
        errors.append('service list differs from reviewed spec')
    for script in (version / 'scripts').glob('*.sh'):
        if script.name in ('start.sh', 'stop.sh', 'restart.sh'):
            errors.append('additional hooks require a verified lifecycle caller: ' + script.name)
        if not script.read_bytes().startswith(b'#!/bin/bash\n') or b'\r' in script.read_bytes():
            errors.append('scripts must use Bash shebang and LF: ' + script.name)
        if not script.stat().st_mode & 0o111:
            errors.append('script must be executable: ' + script.name)
        if not any(url in script.read_text() for url in spec['source_evidence']):
            errors.append('script must cite official action evidence: ' + script.name)
        p = subprocess.run(['bash', '-n', str(script)], capture_output=True, text=True)
        if p.returncode:
            errors.append('shell syntax error: ' + script.name)
    if compose_check and not errors:
        env = os.environ.copy()
        env.update({key: str(field.get('default', '')) for key, field in declared.items()})
        env.update(CONTAINER_NAME='appstore-validation-' + app.name, HOST_IP='127.0.0.1', HOST_ADDRESS='127.0.0.1')
        env_args = ['--env-file', str(version / '.env')] if (version / '.env').exists() else []
        p = subprocess.run(['docker', 'compose', *env_args, '-f', str(compose_path), 'config', '--quiet'],
                           env=env, capture_output=True, text=True, timeout=30)
        if p.returncode:
            errors.append('docker compose config failed: ' + p.stderr.strip())
    return errors


def require_valid(app: Path, root: Path = ROOT) -> None:
    errors = validate(app, root=root)
    if errors:
        raise ValueError('\n'.join(errors))
