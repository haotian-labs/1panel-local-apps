"""Opt-in Docker regression on native Linux files, even on macOS Docker hosts."""

import json
import os
from pathlib import Path
import secrets
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from appstore import ROOT, load_yaml
from smoke_bark import copy_stopped_data, run


@unittest.skipUnless(os.environ.get('RUN_DOCKER_PERMISSION_TEST') == '1',
                     'set RUN_DOCKER_PERMISSION_TEST=1 to test native Linux file permissions in Docker')
class LinuxMigrationTest(unittest.TestCase):
    def test_root_only_database_is_copied_without_relaxing_permissions(self):
        image = load_yaml(ROOT / 'apps/bark/2.4.0/docker-compose.yml')['services']['bark']['image']
        names = ['bark-permission-' + secrets.token_hex(6) for _ in range(2)]
        for name in names:
            run(['docker', 'volume', 'create', '--label', 'appstore.permission-test=true', name])
            self.addCleanup(run, ['docker', 'volume', 'rm', name])

        def container(volume, command, user='0:0'):
            return run(['docker', 'run', '--rm', '--network', 'none', '--user', user,
                        '--entrypoint', '/bin/sh', '--mount', f'type=volume,source={volume},target=/data',
                        image, '-ec', command], check=False)

        # Named volumes are stored in the daemon's Linux filesystem. macOS bind
        # sharing can translate ownership and hide the root:0600 failure seen in CI.
        seed = container(names[0], "printf 'migration-regression' > /data/bark.db; chown 0:0 /data/bark.db; chmod 600 /data/bark.db")
        self.assertEqual(seed.returncode, 0, seed.stderr)
        denied = container(names[0], 'cat /data/bark.db', user='65534:65534')
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn('permission denied', denied.stderr.lower())

        mounts = [Path(json.loads(run(['docker', 'volume', 'inspect', name]).stdout)[0]['Mountpoint']) for name in names]
        copy_stopped_data(mounts[0], mounts[1], image)

        for name in names:
            contents = container(name, "cat /data/bark.db; printf '\n'; stat -c '%a:%u:%g' /data/bark.db")
            self.assertEqual(contents.returncode, 0, contents.stderr)
            self.assertEqual(contents.stdout.splitlines(), ['migration-regression', '600:0:0'])
        denied_after = container(names[1], 'cat /data/bark.db', user='65534:65534')
        self.assertNotEqual(denied_after.returncode, 0)
        self.assertIn('permission denied', denied_after.stderr.lower())


if __name__ == '__main__':
    unittest.main()
