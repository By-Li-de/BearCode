import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.main import _load_env_file


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_symlink_launcher_preserves_workspace_arguments_and_exit_status(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            checkout = base / 'checkout with spaces'
            launcher = checkout / 'bin/bearcode'
            launcher.parent.mkdir(parents=True)
            shutil.copy2(ROOT / 'bin/bearcode', launcher)
            interpreter = checkout / '.venv/bin/python'
            interpreter.parent.mkdir(parents=True)
            interpreter.symlink_to(sys.executable)
            (checkout / 'agents').mkdir()
            (checkout / 'agents/__init__.py').touch()
            (checkout / 'agents/main.py').write_text(
                'import json, os, sys\ndef main():\n'
                '    print(json.dumps({"cwd": os.getcwd(), "args": sys.argv[1:]}))\n'
                '    raise SystemExit(7)\n')
            command = base / 'bearcode'
            command.symlink_to(launcher)
            workspace = base / 'other project'
            workspace.mkdir()
            args = ['--plan', '解释 "quoted text"', r'C:\Users\dev\new.py']
            result = subprocess.run([sys.executable, str(command), *args], cwd=workspace,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertEqual(json.loads(result.stdout), {'cwd': str(workspace.resolve()), 'args': args})

    def test_help_from_another_project_does_not_import_its_agents_package(self):
        with tempfile.TemporaryDirectory() as folder:
            fake_package = Path(folder) / 'agents'
            fake_package.mkdir()
            (fake_package / '__init__.py').write_text('raise RuntimeError("wrong package")')
            result = subprocess.run([sys.executable, str(ROOT / 'bin/bearcode'), '--help'],
                                    cwd=folder, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Usage: bearcode', result.stdout)

    def test_missing_virtual_environment_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as folder:
            launcher = Path(folder) / 'bin/bearcode'
            launcher.parent.mkdir()
            shutil.copy2(ROOT / 'bin/bearcode', launcher)
            result = subprocess.run([sys.executable, str(launcher)], capture_output=True,
                                    text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('README quick start', result.stderr)

    def test_env_file_selection_and_exported_variable_precedence(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            first = Path(folder) / 'project.env'
            second = Path(folder) / 'explicit.env'
            first.write_text('BEAR_TEST_VALUE=project\nBEAR_KEEP=from-file\n')
            second.write_text('BEAR_TEST_VALUE=explicit\nBEAR_KEEP=from-file\n')
            os.environ['BEAR_KEEP'] = 'exported'
            os.environ['BEAR_ENV_FILE'] = str(first)
            _load_env_file(str(second))
            self.assertEqual(os.environ['BEAR_TEST_VALUE'], 'explicit')
            self.assertEqual(os.environ['BEAR_KEEP'], 'exported')
            del os.environ['BEAR_TEST_VALUE']
            _load_env_file()
            self.assertEqual(os.environ['BEAR_TEST_VALUE'], 'project')

    def test_default_env_selection_uses_project_then_checkout(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch('agents.main.find_dotenv', return_value='/project/.env'), \
             patch('agents.main.Path.is_file', return_value=True), \
             patch('agents.main.load_dotenv') as load:
            _load_env_file()
            load.assert_called_once_with(Path('/project/.env'), override=False)
            with patch('agents.main.find_dotenv', return_value=''):
                _load_env_file()
            self.assertEqual(load.call_args.args, (ROOT / '.env',))

    def test_missing_explicit_env_file_does_not_silently_fall_back(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'Environment file does not exist'):
                _load_env_file(str(Path(folder) / 'missing.env'))


if __name__ == '__main__':
    unittest.main()
