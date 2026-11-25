import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import appstore
from package import build
from sync import synchronize


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.app = self.root / 'apps/bark'
        shutil.copytree(appstore.ROOT / 'apps/bark', self.app)
        shutil.copytree(appstore.ROOT / 'specs', self.root / 'specs')
        self.version = self.app / '2.4.0'
        self.target = self.root / 'server/resource/apps/local'

    def errors(self):
        return '\n'.join(appstore.validate(self.app, root=self.root))

    def edit_compose(self, old, new):
        path = self.version / 'docker-compose.yml'
        original = path.read_text()
        self.assertIn(old, original)
        path.write_text(original.replace(old, new))

    def test_current_package_is_valid(self):
        self.assertEqual(self.errors(), '')

    def test_duplicate_yaml_key_is_rejected(self):
        path = self.app / 'data.yml'
        path.write_text(path.read_text() + '\nname: duplicate\n')
        self.assertIn('duplicate YAML key', self.errors())

    def test_legacy_labels_cannot_bypass_locale_check(self):
        path = self.version / 'data.yml'
        value = appstore.load_yaml(path)
        del value['additionalProperties']['formFields'][0]['label']
        path.write_text(appstore.yaml.safe_dump(value, allow_unicode=True))
        self.assertIn('multilingual mapping', self.errors())

    def test_undeclared_compose_variable_is_rejected(self):
        self.edit_compose('${BARK_SERVER_DSN}', '${UNDECLARED}')
        self.assertIn('undeclared Compose variable: UNDECLARED', self.errors())

    def test_fixed_container_name_is_rejected(self):
        self.edit_compose('${CONTAINER_NAME}', 'bark')
        self.assertIn('primary service', self.errors())

    def test_absolute_mount_is_rejected(self):
        self.edit_compose('./data:/data', '/home/bark/data:/data')
        self.assertIn('relative paths', self.errors())

    def test_runtime_database_is_rejected(self):
        (self.version / 'data/bark.db').write_bytes(b'not a distributable')
        self.assertIn('runtime/unwanted file', self.errors())

    def test_nonempty_secret_is_rejected(self):
        with (self.version / '.env').open('a') as f:
            f.write('UNDECLARED_TOKEN=private\n')
        errors = self.errors()
        self.assertIn('nonempty secret', errors)
        self.assertNotIn('private', errors)

    def test_symlink_cannot_leak_into_package(self):
        (self.app / 'leak').symlink_to('/etc/passwd')
        self.assertIn('symlinks are not allowed', self.errors())

    def test_traversal_key_and_version_are_rejected(self):
        with self.assertRaises(ValueError):
            appstore.app_path('../outside', self.root)
        with self.assertRaises(ValueError):
            appstore.selected_version(self.app, '../outside')

    def test_exact_release_tag_must_match_spec(self):
        app, version = appstore.select_tag('bark-2.4.0-r1', self.root)
        self.assertEqual(app, self.app)
        self.assertEqual(version, self.version)
        with self.assertRaises(ValueError):
            appstore.select_tag('bark-2.4.0-r2', self.root)

    def test_archive_is_deterministic_and_has_only_selected_version(self):
        # An additional complete version should not leak into a single-version release.
        shutil.copytree(self.version, self.app / '2.4.1')
        spec = json.loads((self.root / 'specs/bark/2.4.0.json').read_text())
        spec['version'] = '2.4.1'
        (self.root / 'specs/bark/2.4.1.json').write_text(json.dumps(spec))
        first = build(self.app, self.version, self.root / 'out1', self.root)
        second = build(self.app, self.version, self.root / 'out2', self.root)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(first) as z:
            self.assertIn('bark/2.4.0/.env', z.namelist())
            self.assertIn('bark/2.4.0/data/.gitkeep', z.namelist())
            self.assertFalse(any('2.4.1/' in name for name in z.namelist()))
            self.assertIsNone(z.testzip())
        self.assertIn(appstore.digest(first), first.with_suffix('.zip.sha256').read_text())

    def test_sync_preview_writes_nothing(self):
        result = synchronize(self.app, self.target, root=self.root)
        self.assertTrue(result['changes']['added'])
        self.assertFalse(result['applied'])
        self.assertFalse(self.target.exists())

    def test_sync_replaces_one_app_with_backup_and_removes_obsolete_files(self):
        dest = self.target / 'bark'
        dest.mkdir(parents=True)
        (dest / 'obsolete.sh').write_text('obsolete')
        other = self.target / 'another-app'
        other.mkdir()
        (other / 'keep').write_text('preserve')
        result = synchronize(self.app, self.target, True, self.root)
        self.assertTrue(result['applied'])
        self.assertEqual(appstore.file_map(dest), appstore.file_map(self.app))
        self.assertTrue((Path(result['backup']) / 'obsolete.sh').exists())
        self.assertEqual((other / 'keep').read_text(), 'preserve')
        again = synchronize(self.app, self.target, True, self.root)
        self.assertFalse(again['applied'])

    def test_sync_refuses_installed_directory_runtime_data_and_symlinks(self):
        with self.assertRaises(ValueError):
            synchronize(self.app, self.root / 'apps/local', True, self.root)
        dest = self.target / 'bark'
        dest.mkdir(parents=True)
        (dest / 'bark.db').touch()
        with self.assertRaisesRegex(ValueError, 'runtime data'):
            synchronize(self.app, self.target, True, self.root)
        (dest / 'bark.db').unlink()
        (dest / '.env').write_text('BARK_SERVER_DSN=private\n')
        with self.assertRaisesRegex(ValueError, 'credentials'):
            synchronize(self.app, self.target, True, self.root)
        (dest / '.env').unlink()
        (dest / 'leak').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            synchronize(self.app, self.target, True, self.root)

    def test_sync_rolls_back_if_install_rename_fails(self):
        dest = self.target / 'bark'
        dest.mkdir(parents=True)
        (dest / 'old').write_text('original')
        real_replace = appstore.os.replace

        def fail_once(source, target):
            if '.appstore-stage-' in str(source):
                raise OSError('simulated rename failure')
            return real_replace(source, target)

        with mock.patch('sync.os.replace', side_effect=fail_once):
            with self.assertRaises(OSError):
                synchronize(self.app, self.target, True, self.root)
        self.assertEqual((dest / 'old').read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
