"""Regression checks for installer layout, payload and DMG cleanup."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
IFW = ROOT / 'editor/packaging/qtifw'


class InstallerPackagingTests(unittest.TestCase):
    def test_wizard_has_no_unbounded_header_pixmap(self):
        for path in sorted((IFW / 'config').glob('config*.xml')):
            with self.subTest(path=path.name):
                config = ET.parse(path).getroot()
                for tag in ('Logo', 'Banner', 'Watermark', 'Background', 'PageListPixmap'):
                    self.assertIsNone(config.find(tag))
                self.assertTrue(config.findtext('InstallerWindowIcon'))
                self.assertLessEqual(int(config.findtext('WizardDefaultWidth')), 800)
                self.assertLessEqual(int(config.findtext('WizardDefaultHeight')), 600)
                self.assertTrue(config.findtext('RunProgram'))

    @unittest.skipIf(os.name == 'nt', 'Bash helper is used by Linux/macOS')
    def test_installer_rejects_empty_stage_before_binarycreator(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / 'empty'; stage.mkdir()
            tool = Path(tmp) / 'binarycreator'
            tool.write_text('#!/bin/sh\necho unexpected-builder-call\nexit 0\n')
            tool.chmod(0o755)
            run = subprocess.run(['bash', str(IFW / 'build-installer.sh'), str(stage), str(Path(tmp) / 'setup.run'), 'linux', str(tool)], capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertNotIn('unexpected-builder-call', run.stdout)

    @unittest.skipIf(os.name == 'nt', 'Bash helper is used by macOS')
    def test_busy_dmg_retry_and_forced_detach(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            tool = folder / 'hdiutil'
            tool.write_text('#!/bin/sh\necho "$*" >> "$CALL_LOG"\n[ "$2" = "-force" ]\n')
            tool.chmod(0o755)
            sleep = folder / 'sleep'; sleep.write_text('#!/bin/sh\nexit 0\n'); sleep.chmod(0o755)
            log = folder / 'calls'
            env = dict(os.environ, PATH=str(folder) + os.pathsep + os.environ['PATH'], CALL_LOG=str(log))
            run = subprocess.run(['bash', str(IFW / 'detach-dmg.sh'), '/tmp/Qt IFW image'], env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(log.read_text().splitlines(), ['detach /tmp/Qt IFW image'] * 3 + ['detach -force /tmp/Qt IFW image'])

    @unittest.skipIf(os.name == 'nt', 'Bash helper is used by macOS')
    def test_successful_detach_does_not_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool = Path(tmp) / 'hdiutil'
            tool.write_text('#!/bin/sh\necho "$*"\nexit 0\n'); tool.chmod(0o755)
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ['PATH'])
            run = subprocess.run(['bash', str(IFW / 'detach-dmg.sh'), '/tmp/image'], env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0)
            self.assertEqual(run.stdout.strip(), 'detach /tmp/image')


if __name__ == '__main__':
    unittest.main()
