import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('menu_setup', ROOT / 'menu.py')
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)
PLUGIN_ID = 'ipkalid.flatpak-store'


class MenuTests(unittest.TestCase):
    def test_setup_migrates_legacy_and_preserves_comments(self):
        home = Path('/home/person')
        legacy = 'xdg-terminal-exec --app-id=org.omarchy.terminal /home/person/.local/bin/flatpak-store'
        before = {'install.flatpak': {'icon': '󰏖', 'label': 'Flatpak', 'action': legacy},
                  'remove.flatpak': {'icon': '󰏖', 'label': 'Flatpak', 'action': legacy + ' remove'},
                  'custom': {'label': 'My menu'}}
        raw = '// keep this comment\n' + json.dumps(before, ensure_ascii=False, indent=2)
        result = menu.configure(raw, PLUGIN_ID, home)
        data, _ = menu.parse_jsonc(result)
        self.assertEqual(data, {**menu.entries_for(PLUGIN_ID), 'custom': before['custom']})
        self.assertIn('// keep this comment', result)
        self.assertEqual(menu.configure(result, PLUGIN_ID, home), result)

    def test_existing_flatpak_shortcuts_are_retained_and_new_providers_added(self):
        command = 'omarchy-shell shell summon ' + PLUGIN_ID
        original = {action + '.flatpak': {'icon': '󰏖', 'label': 'Flatpak',
                    'action': command + " '{\"action\":\"" + action + "\"}'"}
                    for action in ('install', 'remove', 'update')}
        configured = menu.parse_jsonc(menu.configure(json.dumps(original), PLUGIN_ID, Path('/tmp')))[0]
        self.assertEqual({key: configured[key] for key in original}, original)
        self.assertEqual(len(configured), 8)
        self.assertNotIn('update.mise', configured)
        for provider in ('brew', 'mise'):
            self.assertIn('"provider":"' + provider + '"', configured['install.' + provider]['action'])

    def test_cleanup_entry_positions_and_trailing_commas(self):
        for raw in ('{}', '{ /* empty */ }', '{"custom": 1,}',
                    '{"custom": {"label": "https://example.com/*ok*/",}, // comment\n}',
                    '{"custom": 1 // comment\n}'):
            with self.subTest(raw=raw):
                setup = menu.configure(raw, PLUGIN_ID, Path('/home/person'))
                cleanup = menu.configure(setup, PLUGIN_ID, Path('/home/person'), cleanup=True)
                self.assertEqual(menu.parse_jsonc(cleanup)[0], menu.parse_jsonc(raw)[0])
                if '// comment' in raw:
                    self.assertIn('// comment', cleanup)
                self.assertEqual(menu.configure(cleanup, PLUGIN_ID, Path('/home/person'), cleanup=True), cleanup)
        owned = menu.entries_for(PLUGIN_ID)
        for key, entry in owned.items():
            for trailing in ('', ','):
                raw = '{' + json.dumps(key) + ': ' + json.dumps(entry) + trailing + '\n}'
                self.assertEqual(menu.parse_jsonc(menu.configure(raw, PLUGIN_ID, Path('/tmp'), cleanup=True))[0], {})

    def test_cleanup_preserves_user_edits(self):
        data = menu.entries_for(PLUGIN_ID)
        data['install.flatpak']['label'] = 'Custom install'
        raw = json.dumps(data)
        cleanup = menu.configure(raw, PLUGIN_ID, Path('/tmp'), cleanup=True)
        self.assertEqual(menu.parse_jsonc(cleanup)[0], {'install.flatpak': data['install.flatpak']})

    def test_setup_conflicts_and_duplicate_keys(self):
        for raw in ('{"update.flatpak":{"action":"mine"}}',
                    '{"install.flatpak":null}', '{"x":1,"x":2}',
                    '{"install.brew":{"action":"mine"}}', '{"remove.mise":{"action":"mine"}}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                menu.configure(raw, PLUGIN_ID, Path('/tmp'))

    def test_root_migration_preserves_customized_root(self):
        for root in (menu.old_panel_entry(PLUGIN_ID), {'action': 'mine'}):
            raw = '// retain\n' + json.dumps({'flatpak-store': root})
            configured = menu.configure(raw, PLUGIN_ID, Path('/tmp'))
            data, _ = menu.parse_jsonc(configured)
            self.assertIn('// retain', configured)
            self.assertEqual(data.get('flatpak-store'), None if root == menu.old_panel_entry(PLUGIN_ID) else root)
            self.assertEqual(menu.status(configured, PLUGIN_ID, Path('/tmp'))['status'], 'complete')

    def test_status_recognizes_pending_migration(self):
        entries = menu.entries_for(PLUGIN_ID)
        entries['flatpak-store'] = menu.old_panel_entry(PLUGIN_ID)
        state = menu.status(json.dumps(entries), PLUGIN_ID, Path('/tmp'))
        self.assertEqual(state['status'], 'missing')
        self.assertTrue(state['legacyPanel'])

    def test_json_status_is_read_only_and_setup_reports_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            path = home / '.config/omarchy/extensions/omarchy-menu.jsonc'
            command = [sys.executable, '-B', str(ROOT / 'menu.py')]
            def invoke(action):
                result = subprocess.run([*command, action, '--home', temporary, '--json'], capture_output=True, text=True)
                return result.returncode, json.loads(result.stdout)
            code, result = invoke('status')
            self.assertEqual(code, 0)
            self.assertEqual(set(result['missing']), set(menu.entries_for(PLUGIN_ID)))
            self.assertEqual(list(home.iterdir()), [])
            self.assertTrue(invoke('setup')[1]['changed'])
            self.assertEqual(invoke('status')[1]['status'], 'complete')
            self.assertFalse(invoke('setup')[1]['changed'])
            original = '// untouched\n{"update.flatpak":{"action":"custom"}}'
            path.write_text(original)
            state = invoke('status')[1]
            self.assertEqual(state['conflicts'], ['update.flatpak'])
            code, result = invoke('setup')
            self.assertEqual(code, 1)
            self.assertFalse(result['ok'])
            self.assertIn('update.flatpak', result['error'])
            self.assertEqual(path.read_text(), original)
            self.assertEqual(list(path.parent.glob('*.bak.*')), [])
            path.write_text('{bad json')
            self.assertFalse(invoke('status')[1]['ok'])
            path.unlink()
            path.mkdir()
            self.assertFalse(invoke('setup')[1]['ok'])

    def test_cli_dry_run_backup_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            path = home / '.config/omarchy/extensions/omarchy-menu.jsonc'
            path.parent.mkdir(parents=True)
            original = '// preserved\n{"custom": 1}\n'
            path.write_text(original)
            command = [sys.executable, str(ROOT / 'menu.py')]
            subprocess.run([*command, 'setup', '--home', temporary, '--dry-run'], check=True, capture_output=True)
            self.assertEqual(path.read_text(), original)
            for _ in range(2):
                subprocess.run([*command, 'setup', '--home', temporary], check=True, capture_output=True)
            self.assertEqual(len(list(path.parent.glob('*.bak.*'))), 1)
            self.assertFalse((home / '.local/bin/flatpak-store').exists())
            subprocess.run([*command, 'cleanup', '--home', temporary], check=True, capture_output=True)
            self.assertEqual(menu.parse_jsonc(path.read_text())[0], {'custom': 1})


class PluginTests(unittest.TestCase):
    def test_dependency_probe_without_python_or_flatpak(self):
        dependencies = ('flatpak', 'brew', 'mise', 'fzf', 'python3', 'timeout', 'xdg-terminal-exec')
        cases = [(), dependencies, *(tuple(name for name in dependencies if name != missing)
                                     for missing in dependencies)]
        with tempfile.TemporaryDirectory() as temporary:
            for available in cases:
                for stub in Path(temporary).iterdir():
                    stub.unlink()
                for command in available:
                    stub = Path(temporary) / command
                    stub.write_text('#!/bin/bash\nexit 99\n')
                    stub.chmod(0o755)
                result = subprocess.run(['/bin/bash', str(ROOT / 'check-dependencies')],
                                        env={**os.environ, 'PATH': temporary}, check=True,
                                        capture_output=True, text=True)
                self.assertEqual(json.loads(result.stdout), {name: name in available for name in dependencies})

    def test_brew_probe_finds_custom_prefix_without_executing_brew(self):
        with tempfile.TemporaryDirectory(prefix='brew prefix ') as temporary:
            prefix = Path(temporary)
            (prefix / 'bin').mkdir()
            brew = prefix / 'bin/brew'
            brew.write_text('#!/bin/bash\nprintf ran > "' + str(prefix / 'executed') + '"\n')
            brew.chmod(0o755)
            result = subprocess.run(['/bin/bash', str(ROOT / 'check-dependencies'), 'brew'],
                                    env={**os.environ, 'PATH': '/usr/bin:/bin', 'HOMEBREW_PREFIX': temporary},
                                    capture_output=True, text=True, check=True)
            self.assertTrue(json.loads(result.stdout)['brew'])
            self.assertFalse((prefix / 'executed').exists())
            # Other providers retain their inherited environment.
            result = subprocess.run(['/bin/bash', str(ROOT / 'check-dependencies'), 'mise'],
                                    env={**os.environ, 'PATH': temporary, 'HOMEBREW_PREFIX': temporary},
                                    capture_output=True, text=True, check=True)
            self.assertFalse(json.loads(result.stdout)['brew'])

    def test_action_payloads_and_argv(self):
        subprocess.run(['node', str(ROOT / 'tests/actions.test.js')], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
