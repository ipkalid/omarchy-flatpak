import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', ROOT / 'install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

REF_A = 'app/org.example.One/x86_64/stable'
REF_B = 'app/org.example.Two/x86_64/beta'
CATALOG = f'{REF_A}\tApp One\tFirst application\n{REF_B}\tApp Two\tSecond application\n'

STUB = r'''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys, time
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['CALLS'], 'a') as out:
    out.write(json.dumps([name, *args]) + '\n')
if name == 'fzf':
    if os.environ.get('PICK') == 'cancel-loading':
        deadline = time.monotonic() + 2
        while not pathlib.Path(os.environ['ROWS'] + '.loading').exists():
            if time.monotonic() > deadline: sys.exit(2)
            time.sleep(.01)
        sys.exit(130)
    rows = sys.stdin.read()
    pathlib.Path(os.environ['ROWS']).write_text(rows)
    action = next(arg.removeprefix('--bind=load:transform:') for arg in args
                  if arg.startswith('--bind=load:transform:'))
    loaded = subprocess.check_output(action, shell=True, text=True).strip()
    pathlib.Path(os.environ['ROWS'] + '.action').write_text(loaded)
    if loaded == 'abort': sys.exit(130)
    mode = os.environ.get('PICK', 'all')
    if mode == 'cancel': sys.exit(130)
    if mode == 'none': sys.exit(1)
    if mode == 'error': sys.exit(2)
    if mode == 'empty': sys.exit(0)
    if mode == 'invalid': print('app/org.example.Other/x86_64/stable\tOther'); sys.exit(0)
    if mode == 'runtime': print('runtime/org.example.One/x86_64/stable\tRuntime'); sys.exit(0)
    if mode == 'duplicate': print(rows + rows, end=''); sys.exit(0)
    print(rows, end='')
elif args[0] == 'remotes':
    print('other' if os.environ.get('NO_REMOTE') else 'flathub')
elif args[0] == 'remote-ls':
    pathlib.Path(os.environ['ROWS'] + '.loading').touch()
    time.sleep(float(os.environ.get('LOAD_DELAY', '0')))
    if os.environ.get('OFFLINE') and '--cached' not in args:
        print('Network unavailable', file=sys.stderr); sys.exit(1)
    if os.environ.get('NO_CACHE') and '--cached' in args: sys.exit(1)
    if not os.environ.get('EMPTY_CATALOG'): print(os.environ['CATALOG'], end='')
elif args[0] == 'list':
    if os.environ.get('LIST_ERROR'): sys.exit(1)
    if '--columns=ref,name,description' in args:
        print(os.environ.get('INSTALLED_ROWS', ''.join(line.removeprefix('app/')
              for line in os.environ['CATALOG'].splitlines(keepends=True))), end='')
    else: print('org.example.One/x86_64/stable')
elif args[0] == 'install':
    sys.exit(int(os.environ.get('INSTALL_EXIT', '0')))
elif args[0] == 'uninstall':
    sys.exit(int(os.environ.get('UNINSTALL_EXIT', '0')))
elif args[0] == 'update':
    print('Nothing to do.' if os.environ.get('NO_UPDATES') else 'Updating apps and runtimes')
    sys.exit(int(os.environ.get('UPDATE_EXIT', '0')))
elif args[0] in ('info', 'remote-info'):
    print(os.environ.get('METADATA', 'Version: 1.2\nLicense: MIT\nCommit: secret-hash\nInstalled Size: 10 MB'))
    sys.exit(int(os.environ.get('PREVIEW_EXIT', '0')))
'''


class PickerTests(unittest.TestCase):
    def run_picker(self, mode=None, **overrides):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            commands = base / 'bin'
            commands.mkdir()
            for name in ('flatpak', 'fzf'):
                path = commands / name
                path.write_text(STUB)
                path.chmod(0o755)
            env = dict(os.environ, PATH=f'{commands}:{os.environ["PATH"]}',
                       CALLS=str(base / 'calls'), ROWS=str(base / 'rows'),
                       CATALOG=CATALOG, TMPDIR=temporary, **overrides)
            command = ['bash', str(ROOT / 'flatpak-store')]
            if isinstance(mode, list): command.extend(mode)
            elif mode: command.append(mode)
            result = subprocess.run(command, env=env,
                                    capture_output=True, text=True, timeout=10)
            calls = [json.loads(line) for line in (base / 'calls').read_text().splitlines()] if (base / 'calls').exists() else []
            rows = (base / 'rows').read_text() if (base / 'rows').exists() else ''
            self.loaded_action = (base / 'rows.action').read_text() if (base / 'rows.action').exists() else ''
            self.assertEqual(list(base.glob('flatpak-store.*')), [], 'Temporary data leaked')
            return result, calls, rows

    def test_picker_opens_before_catalog_finishes(self):
        result, calls, _ = self.run_picker(LOAD_DELAY='0.25', PICK='cancel')
        self.assertEqual(result.returncode, 0, result.stderr)
        picker_index = next(i for i, c in enumerate(calls) if c[0] == 'fzf')
        installed_index = next(i for i, c in enumerate(calls) if c[:2] == ['flatpak', 'list'])
        self.assertLess(picker_index, installed_index)
        self.assertNotIn('Loading Flathub', result.stderr)

    def test_escape_during_loading_returns_immediately(self):
        start = time.monotonic()
        result, calls, _ = self.run_picker(LOAD_DELAY='5', PICK='cancel-loading')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(time.monotonic() - start, 2)
        self.assertFalse(any(c[:2] == ['flatpak', 'install'] for c in calls))

    def test_exact_refs_and_installed_marker(self):
        result, calls, rows = self.run_picker()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(['flatpak', 'install', '--system', '--assumeyes', 'flathub', REF_A, REF_B], calls)
        self.assertIn('First application\t[installed]', rows)
        self.assertNotIn('Second application\t[installed]', rows)
        picker = next(call for call in calls if call[0] == 'fzf')
        self.assertIn('--multi', picker)
        self.assertIn('--preview', picker)
        self.assertIn('--preview install {1}', picker[picker.index('--preview') + 1])

    @unittest.skipUnless(shutil.which('fzf'), 'fzf is required to verify search matching')
    def test_search_matches_names_only(self):
        for mode in (None, 'remove'):
            result, calls, rows = self.run_picker(mode)
            self.assertEqual(result.returncode, 0, result.stderr)
            picker_args = next(call[1:] for call in calls if call[0] == 'fzf')
            for query, expected in (('App One', [REF_A]), ('ApTw', [REF_B]),
                                    ('First application', []), ('org.example', [])):
                with self.subTest(mode=mode, query=query):
                    filtered = subprocess.run(
                        ['fzf', *picker_args, '--filter=' + query], input=rows,
                        capture_output=True, text=True, timeout=10,
                        env=dict(os.environ, FZF_DEFAULT_OPTS='', FZF_DEFAULT_OPTS_FILE=''))
                    self.assertEqual(filtered.returncode, 0 if expected else 1, filtered.stderr)
                    self.assertEqual([line.split('\t')[0] for line in filtered.stdout.splitlines()],
                                     expected)

    def test_cancellation_and_empty_selection(self):
        for mode in ('cancel', 'none', 'empty'):
            with self.subTest(mode=mode):
                result, calls, _ = self.run_picker(PICK=mode)
                self.assertEqual(result.returncode, 0)
                self.assertFalse(any(c[:2] == ['flatpak', 'install'] for c in calls))

    def test_picker_error_and_invalid_selection(self):
        for mode in ('error', 'invalid'):
            with self.subTest(mode=mode):
                result, calls, _ = self.run_picker(PICK=mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(c[:2] == ['flatpak', 'install'] for c in calls))

    def test_cached_fallback_label(self):
        result, calls, _ = self.run_picker(OFFLINE='1', PICK='cancel')
        self.assertEqual(result.returncode, 0)
        self.assertTrue(any('--cached' in c for c in calls if c[:2] == ['flatpak', 'remote-ls']))
        self.assertIn('STALE CACHE', self.loaded_action)

    def test_unavailable_catalog_and_setup_errors(self):
        for overrides in ({'OFFLINE': '1', 'NO_CACHE': '1'}, {'EMPTY_CATALOG': '1'},
                          {'NO_REMOTE': '1'}, {'LIST_ERROR': '1'}):
            with self.subTest(overrides=overrides):
                result, calls, _ = self.run_picker(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.loaded_action, 'abort')
                self.assertFalse(any(c[:2] == ['flatpak', 'install'] for c in calls))

    def test_install_failure_is_preserved(self):
        result, _, _ = self.run_picker(INSTALL_EXIT='7')
        self.assertEqual(result.returncode, 7)
        self.assertIn('did not complete successfully', result.stderr)
        self.assertNotIn('Flatpak finished', result.stdout)

    def test_remove_exact_refs_confirmation_and_local_data(self):
        result, calls, rows = self.run_picker('remove', NO_REMOTE='1', OFFLINE='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        removal = next(c for c in calls if c[:2] == ['flatpak', 'uninstall'])
        # Exact argv also guards against adding data deletion, force, or confirmation bypass flags.
        self.assertEqual(removal, ['flatpak', 'uninstall', '--system', '--app', REF_A, REF_B])
        self.assertIn(['flatpak', 'list', '--system', '--app', '--columns=ref,name,description'], calls)
        self.assertFalse(any(c[0] == 'flatpak' and c[1] in
                             ('remotes', 'remote-ls', 'remote-info', 'install') for c in calls))
        self.assertIn('App Two\tSecond application', rows)
        picker = next(c for c in calls if c[0] == 'fzf')
        self.assertIn('--color=pointer:red,marker:red', picker)
        self.assertIn('--preview remove {1}', picker[picker.index('--preview') + 1])
        self.assertIn('alt-d:preview-half-page-down,alt-u:preview-half-page-up',
                      next(arg for arg in picker if arg.startswith('--bind=alt-p:')))

    def test_remove_cancellation_and_empty_selection(self):
        for pick in ('cancel', 'none', 'empty'):
            with self.subTest(pick=pick):
                result, calls, _ = self.run_picker('remove', PICK=pick)
                self.assertEqual(result.returncode, 0)
                self.assertFalse(any(c[:2] == ['flatpak', 'uninstall'] for c in calls))

    def test_remove_rejects_invalid_selection_and_picker_failure(self):
        for pick in ('invalid', 'runtime', 'error'):
            with self.subTest(pick=pick):
                result, calls, _ = self.run_picker('remove', PICK=pick)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(c[:2] == ['flatpak', 'uninstall'] for c in calls))

    def test_remove_normalizes_refs_and_deduplicates(self):
        result, calls, _ = self.run_picker('remove', INSTALLED_ROWS=CATALOG, PICK='duplicate')
        self.assertEqual(result.returncode, 0)
        self.assertIn(['flatpak', 'uninstall', '--system', '--app', REF_A, REF_B], calls)

    def test_remove_empty_installation(self):
        result, calls, _ = self.run_picker('remove', INSTALLED_ROWS='')
        self.assertEqual(result.returncode, 0)
        self.assertIn('No system Flatpak applications are installed', result.stderr)
        self.assertFalse(any(c[:2] == ['flatpak', 'uninstall'] for c in calls))
        self.assertEqual(self.loaded_action, 'abort')

    def test_remove_list_failure(self):
        result, calls, _ = self.run_picker('remove', LIST_ERROR='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Could not list installed apps', result.stderr)
        self.assertFalse(any(c[:2] == ['flatpak', 'uninstall'] for c in calls))
        self.assertEqual(self.loaded_action, 'abort')

    def test_remove_failure_is_preserved(self):
        result, _, _ = self.run_picker('remove', UNINSTALL_EXIT='9')
        self.assertEqual(result.returncode, 9)
        self.assertIn('did not complete successfully', result.stderr)
        self.assertNotIn('Flatpak finished', result.stdout)

    def test_preview_uses_read_only_commands_and_omarchy_labels(self):
        for mode in ('install', 'remove'):
            with self.subTest(mode=mode):
                result, calls, _ = self.run_picker(
                    ['--preview', mode, REF_A, 'App One', 'First application', '[installed]'])
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = ['flatpak', 'info', '--system', REF_A] if mode == 'remove' else [
                    'flatpak', 'remote-info', '--system', '--cached', 'flathub', REF_A]
                self.assertEqual(calls, [expected])
                self.assertIn('Name            : App One', result.stdout)
                self.assertIn('Description     : First application', result.stdout)
                self.assertIn('Status          : Installed', result.stdout)
                self.assertIn('Version         : 1.2', result.stdout)
                self.assertNotIn('secret-hash', result.stdout)

    def test_preview_failure_retains_app_identity(self):
        result, _, _ = self.run_picker(
            ['--preview', 'install', REF_B, 'App Two', 'Second application', ''], PREVIEW_EXIT='1')
        self.assertEqual(result.returncode, 0)
        self.assertIn('App Two', result.stdout)
        self.assertIn('Second application', result.stdout)
        self.assertIn('Additional details are unavailable', result.stdout)

    def test_preview_rejects_untrusted_ref_without_running_flatpak(self):
        result, calls, _ = self.run_picker(
            ['--preview', 'remove', '--all', 'Name', 'Description', ''])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])

    def test_update_all_only_invokes_system_update(self):
        for extra in ({}, {'NO_UPDATES': '1'}, {'NO_REMOTE': '1'}):
            with self.subTest(extra=extra):
                result, calls, _ = self.run_picker('update', **extra)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [['flatpak', 'update', '--system', '--assumeyes']])

    def test_update_failure_status_and_output(self):
        result, calls, _ = self.run_picker('update', UPDATE_EXIT='8')
        self.assertEqual(result.returncode, 8)
        self.assertEqual(calls, [['flatpak', 'update', '--system', '--assumeyes']])
        self.assertIn('update did not complete successfully', result.stderr)
        self.assertNotIn('Flatpak finished', result.stdout)


class InstallerTests(unittest.TestCase):
    entry = {'icon': '󰏖', 'label': 'Flatpak', 'action': 'flatpak-store'}

    def test_jsonc_preserves_comments_strings_and_existing_entries(self):
        for raw in ('{}\n', '{/* empty */}\n',
                    '{"existing": {"action": "https://example.org/a/*b*/"}}\n',
                    '{\n // keep me\n "existing": {"label": "Name",}, // end\n}\n',
                    '{"existing": 1 // trailing comment\n}\n'):
            with self.subTest(raw=raw):
                before, _ = installer.parse_jsonc(raw)
                merged = installer.merge_menu(raw, self.entry)
                after, _ = installer.parse_jsonc(merged)
                self.assertEqual(after, {**before, installer.KEY: self.entry})
                self.assertEqual(installer.merge_menu(merged, self.entry), merged)
                if '// keep me' in raw: self.assertIn('// keep me', merged)
                if '// end' in raw: self.assertIn('// end', merged)

    def test_conflict_and_invalid_config(self):
        for raw in ('{"install.flatpak": {"action": "custom"}}', '[1]', '{broken}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                installer.merge_menu(raw, self.entry)

    def test_staged_install_backup_idempotence_and_dry_run(self):
        with tempfile.TemporaryDirectory(prefix='flatpak home ') as temporary:
            home = Path(temporary)
            menu = home / '.config/omarchy/extensions/omarchy-menu.jsonc'
            menu.parent.mkdir(parents=True)
            original = '{"setup.keybindings.gui": {"action": "existing"}}\n'
            menu.write_text(original)
            command = ['python3', str(ROOT / 'install.py'), '--home', temporary]
            subprocess.run([*command, '--dry-run'], check=True, capture_output=True)
            self.assertEqual(menu.read_text(), original)
            self.assertFalse((home / '.local/bin/flatpak-store').exists())
            for _ in range(2): subprocess.run(command, check=True, capture_output=True)
            launcher = home / '.local/bin/flatpak-store'
            self.assertEqual(launcher.read_bytes(), (ROOT / 'flatpak-store').read_bytes())
            self.assertTrue(os.access(launcher, os.X_OK))
            data, _ = installer.parse_jsonc(menu.read_text())
            self.assertEqual(data['setup.keybindings.gui']['action'], 'existing')
            self.assertIn("'", data[installer.KEY]['action'], 'Path with spaces must be quoted')
            self.assertEqual(data['remove.flatpak']['action'], data[installer.KEY]['action'] + ' remove')
            backups = list(menu.parent.glob('*.bak.*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), original)

    def test_upgrade_existing_install_only_menu(self):
        entry = self.entry
        raw = '// existing menu\n' + json.dumps({installer.KEY: entry, 'custom': {'label': 'Keep'}})
        removal = {**entry, 'action': 'flatpak-store remove'}
        merged = installer.merge_menu(raw, entry)
        merged = installer.merge_menu(merged, removal, 'remove.flatpak')
        data, _ = installer.parse_jsonc(merged)
        self.assertEqual(data[installer.KEY], entry)
        self.assertEqual(data['custom'], {'label': 'Keep'})
        self.assertEqual(data['remove.flatpak'], removal)
        self.assertIn('// existing menu', merged)

    def test_conflicting_removal_entry_leaves_files_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            menu = home / '.config/omarchy/extensions/omarchy-menu.jsonc'
            menu.parent.mkdir(parents=True)
            original = '{"remove.flatpak": {"action": "custom"}}\n'
            menu.write_text(original)
            launcher = home / '.local/bin/flatpak-store'
            launcher.parent.mkdir(parents=True)
            launcher.write_text('existing launcher')
            result = subprocess.run(['python3', str(ROOT / 'install.py'), '--home', temporary],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('remove.flatpak already exists', result.stderr)
            self.assertEqual(menu.read_text(), original)
            self.assertEqual(launcher.read_text(), 'existing launcher')
            self.assertEqual(list(menu.parent.glob('*.bak.*')), [])


if __name__ == '__main__':
    unittest.main()
