import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from desktop import build
from tools import bump_version

SAMPLE = """# Changelog

## [Unreleased]

### Added
- New thing.

## [0.1.0] - 2026-10-11

### Added
- First.

[Unreleased]: https://github.com/andy5090/lowsky/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/andy5090/lowsky/releases/tag/v0.1.0
"""


class VersioningTests(unittest.TestCase):
    def test_every_version_field_matches_latest_changelog_release(self):
        found = bump_version.current_versions()
        values = {value for versions in found.values() for value in versions}
        self.assertEqual(len(values), 1, found)
        self.assertEqual(bump_version.released_versions()[0], values.pop())
        self.assertTrue(all(found.values()), 'every tracked file must expose its version field')

    def test_release_moves_unreleased_entries_and_updates_links(self):
        text = bump_version.release_changelog(SAMPLE, '0.2.0', '2026-10-12')
        self.assertIn('## [Unreleased]\n\n## [0.2.0] - 2026-10-12\n\n### Added\n- New thing.\n\n## [0.1.0]', text)
        self.assertIn('[Unreleased]: https://github.com/andy5090/lowsky/compare/v0.2.0...HEAD\n'
                      '[0.2.0]: https://github.com/andy5090/lowsky/compare/v0.1.0...v0.2.0\n', text)
        self.assertEqual(bump_version.released_versions(text), ['0.2.0', '0.1.0'])

    def test_release_rejects_empty_or_duplicate_versions(self):
        empty = SAMPLE.replace('### Added\n- New thing.\n\n', '', 1)
        with self.assertRaises(ValueError):
            bump_version.release_changelog(empty, '0.2.0', '2026-10-12')
        with self.assertRaises(ValueError):
            bump_version.release_changelog(SAMPLE, '0.1.0', '2026-10-12')

    def test_writers_round_trip_every_field(self):
        for path, (reader, writer) in bump_version.FIELDS.items():
            original = (bump_version.ROOT / path).read_text(encoding='utf-8')
            with tempfile.TemporaryDirectory() as directory, patch.object(bump_version, 'ROOT', Path(directory)):
                target = Path(directory) / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(writer(original, '9.8.7'), encoding='utf-8')
                self.assertEqual(set(reader(path)), {'9.8.7'}, path)


class InstallerPublishTests(unittest.TestCase):
    def test_publish_replaces_previous_copy_without_leaving_partials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installer = root / 'LOW SKY_0.2.0_aarch64.dmg'
            installer.write_bytes(b'new build')
            folder = root / 'shared'
            folder.mkdir()
            (folder / installer.name).write_bytes(b'old build')
            build.publish(installer, folder)
            self.assertEqual((folder / installer.name).read_bytes(), b'new build')
            self.assertEqual(sorted(path.name for path in folder.iterdir()), [installer.name])
            with self.assertRaises(RuntimeError):
                build.publish(installer, root / 'missing')

    def test_publish_dir_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            setting = Path(directory) / 'installer-publish-dir.txt'
            setting.write_text('/from/file\n', encoding='utf-8')
            with patch.object(build, 'PUBLISH_DIR_FILE', setting), patch.dict(os.environ, {}, clear=False):
                os.environ.pop('LOWSKY_INSTALLER_DIR', None)
                self.assertEqual(build.publish_dir(None), Path('/from/file'))
                os.environ['LOWSKY_INSTALLER_DIR'] = '/from/env'
                self.assertEqual(build.publish_dir(None), Path('/from/env'))
                self.assertEqual(build.publish_dir('/from/flag'), Path('/from/flag'))
            with patch.object(build, 'PUBLISH_DIR_FILE', Path(directory) / 'absent.txt'), \
                    patch.dict(os.environ, {'LOWSKY_INSTALLER_DIR': ''}):
                self.assertIsNone(build.publish_dir(None))


if __name__ == '__main__':
    unittest.main()
