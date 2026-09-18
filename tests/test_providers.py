"""End-to-end provider flows with fake package managers and a controllable picker."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('package_store', ROOT / 'package_store.py')
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)

STUB = r'''#!/usr/bin/env python3
import json, os, pathlib, signal, subprocess, sys, time
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['CALLS'], 'a') as log:
    log.write(json.dumps([name, args, os.getcwd()]) + '\n')
if name == 'fzf':
    step_file = pathlib.Path(os.environ['STEPS'])
    step = int(step_file.read_text()) if step_file.exists() else 0
    step_file.write_text(str(step + 1))
    choices = json.loads(os.environ.get('CHOICES', '["0", "0"]'))
    choice = choices[min(step, len(choices) - 1)]
    if choice == 'early':
        time.sleep(.3)
        sys.exit(130)
    rows = sys.stdin.read().splitlines()
    load = next(a for a in args if a.startswith('--bind=load:transform:'))
    action = subprocess.check_output(load.split('load:transform:', 1)[1], shell=True, text=True)
    if action.strip() == 'abort': sys.exit(130)
    if choice == 'cancel': sys.exit(130)
    if choice == 'error': sys.exit(2)
    if choice == 'invalid': print('99999\tbad'); sys.exit(0)
    if choice == 'none': sys.exit(0)
    for i in choice.split(','): print(rows[int(i)])
    sys.exit(0)
if name == 'timeout':
    if os.environ.get('SHORT_TIMEOUT'):
        args[2] = '0.1s'
    os.execv('/usr/bin/timeout', ['timeout', *args])
if os.environ.get('FAIL') == name + ':' + args[0]:
    print('Simulated package manager failure', file=sys.stderr)
    sys.exit(7)
if os.environ.get('SLOW') and args[0] == 'info':
    pathlib.Path(os.environ['PIDFILE']).write_text(str(os.getpid()))
    time.sleep(20)
if name == 'brew':
    if args[0] == 'info':
        if '--json=v2' in args:
            print(json.dumps({'formulae': [] if os.environ.get('EMPTY') else [
                {'name': 'alpha', 'full_name': 'alpha', 'desc': 'Alpha utility', 'installed': [{'version': '1.0'}]},
                {'name': 'beta', 'full_name': 'owner/tap/beta', 'desc': 'Beta utility', 'installed': [{'version': '2.0'}]}]}))
        else: print('Formula details\nVersion: 1.0')
    elif args[0] == 'formulae':
        print('alpha\nowner/tap/beta\npython@3.13')
elif name == 'mise':
    if args[0] == 'ls':
        print(json.dumps({} if os.environ.get('EMPTY') else {'node': [
            {'version': '20.1.0', 'installed': True, 'active': True},
            {'version': '22.3.0', 'installed': True, 'active': False},
            {'version': '99.0.0', 'installed': False, 'active': True}]}))
    elif args[0] == 'registry':
        print(json.dumps([{'short': 'node', 'description': 'JavaScript runtime', 'backends': ['core:node']}]))
    elif args[0] == 'ls-remote': print('20.1.0\n22.3.0\n24.0.0-rc.1')
'''


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='provider test ')
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        for name in ('brew', 'mise', 'fzf', 'timeout'):
            path = self.bin / name
            path.write_text(STUB)
            path.chmod(0o755)
        self.env = {**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH'],
                    'HOME': str(self.home), 'CALLS': str(self.home / 'calls'),
                    'STEPS': str(self.home / 'steps'), 'PIDFILE': str(self.home / 'pid')}

    def run_store(self, provider='brew', action='install', choices=('0', '0'), answer='y\n', **env):
        result = subprocess.run(['bash', str(ROOT / (provider + '-store')), action],
                                env={**self.env, 'CHOICES': json.dumps(choices), **env},
                                input=answer, capture_output=True, text=True, timeout=8)
        calls = [json.loads(line) for line in (self.home / 'calls').read_text().splitlines()] if (self.home / 'calls').exists() else []
        return result, calls

    def transactions(self, calls):
        return [[name, *args] for name, args, cwd in calls
                if name in ('brew', 'mise') and args[0] in ('install', 'uninstall', 'update', 'upgrade', 'use', 'unuse')]

    def test_brew_install_exact_formulae(self):
        result, calls = self.run_store(choices=('0,1,1,2',))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.transactions(calls), [['brew', 'install', '--formula', 'alpha', 'owner/tap/beta', 'python@3.13']])
        self.assertIn('--multi', next(args for name, args, _ in calls if name == 'fzf'))

    def test_brew_remove_and_confirmation(self):
        result, calls = self.run_store(action='remove', choices=('1',))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.transactions(calls), [['brew', 'uninstall', '--formula', 'owner/tap/beta']])
        self.assertIn('owner/tap/beta', result.stdout)
        self.assertFalse(any(name == 'brew' and args[0] == 'formulae' for name, args, _ in calls))

    def test_declining_removal(self):
        result, calls = self.run_store(action='remove', answer='n\n')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.transactions(calls), [])

    def test_update_refresh_then_upgrade(self):
        result, calls = self.run_store(action='update')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.transactions(calls), [['brew', 'update'], ['brew', 'upgrade', '--formula']])
        self.assertFalse(any(name == 'fzf' for name, _, _ in calls))

    def test_failed_refresh_prevents_upgrade(self):
        result, calls = self.run_store(action='update', FAIL='brew:update')
        self.assertEqual(result.returncode, 7)
        self.assertEqual(self.transactions(calls), [['brew', 'update']])

    def test_mise_install_exact_version_only_from_home(self):
        result, calls = self.run_store(provider='mise', choices=('0', '1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.transactions(calls), [['mise', 'install', 'node@24.0.0-rc.1']])
        self.assertTrue(all(cwd == str(self.home) for name, _, cwd in calls if name == 'mise'))
        self.assertTrue(all('--multi' not in args for name, args, _ in calls if name == 'fzf'))

    def test_mise_latest_installs_latest_without_changing_defaults(self):
        result, calls = self.run_store(provider='mise', choices=('0', '0'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.transactions(calls), [['mise', 'install', 'node@latest']])
        pickers = [args for name, args, _ in calls if name == 'fzf']
        self.assertFalse(any(arg.startswith('--layout') for args in pickers for arg in args))

    def test_mise_version_order_and_latest_option(self):
        installed = {'node': [{'version': version, 'installed': True}
                              for version in ('9.0.0', '10.0.0')]}
        with patch.object(store, 'mise_installed', return_value=installed), \
                patch.object(store, 'query', return_value='9.0.0\n10.0.0\n22.0.0-rc.1\n22.0.0\n'):
            rows = store.mise_catalog('install', 'versions', 'node')
            self.assertEqual([item['key'] for item in rows],
                             ['node@latest', 'node@22.0.0', 'node@22.0.0-rc.1', 'node@10.0.0', 'node@9.0.0'])
            self.assertEqual(rows[0]['name'], 'Latest')
            self.assertEqual(rows[0]['status'], 'Resolved when installing')
            self.assertTrue(rows[-1]['installed'])
            removal = store.mise_catalog('remove', 'versions', 'node')
            self.assertEqual([item['key'] for item in removal], ['node@10.0.0', 'node@9.0.0'])

    def test_mise_remove_only_selected_installed_versions(self):
        result, calls = self.run_store(provider='mise', action='remove', choices=('0', '0,1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.transactions(calls), [['mise', 'uninstall', 'node@22.3.0', 'node@20.1.0']])
        self.assertFalse(any(name == 'mise' and args[0] in ('registry', 'ls-remote') for name, args, _ in calls))
        self.assertIn('configuration stays unchanged', result.stdout)

    def test_mise_version_cancel_changes_nothing(self):
        result, calls = self.run_store(provider='mise', choices=('0', 'cancel'))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.transactions(calls), [])

    def test_mise_update_rejected(self):
        result, calls = self.run_store(provider='mise', action='update')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])

    def test_picker_cancel(self):
        result, calls = self.run_store(choices=('cancel',))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.transactions(calls), [])

    def test_invalid_selection(self):
        result, calls = self.run_store(choices=('invalid',))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.transactions(calls), [])

    def test_picker_failure(self):
        result, calls = self.run_store(choices=('error',))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.transactions(calls), [])

    def test_catalog_error_is_not_silent_cancellation(self):
        result, calls = self.run_store(FAIL='brew:info')
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertIn('Simulated', result.stderr)
        self.assertEqual(self.transactions(calls), [])

    def test_empty_removal(self):
        result, calls = self.run_store(provider='mise', action='remove', EMPTY='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('No installed', result.stdout)
        self.assertEqual(self.transactions(calls), [])

    def test_transaction_failure(self):
        result, calls = self.run_store(FAIL='brew:install')
        self.assertEqual(result.returncode, 7)
        self.assertIn('did not complete successfully', result.stderr)
        self.assertNotIn('brew finished', result.stdout)

    def test_cancel_terminates_pending_lookup(self):
        before = time.monotonic()
        result, calls = self.run_store(choices=('early',), SLOW='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(time.monotonic() - before, 3)
        self.assertEqual(self.transactions(calls), [])
        pid = int((self.home / 'pid').read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_termination_cleans_up_pending_lookup(self):
        process = subprocess.Popen(['bash', str(ROOT / 'brew-store')],
                                   env={**self.env, 'SLOW': '1'}, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 3
            while not (self.home / 'pid').exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue((self.home / 'pid').exists())
            pid = int((self.home / 'pid').read_text())
            process.terminate()
            process.communicate(timeout=3)
            self.assertEqual(process.returncode, 143)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_lookup_timeout(self):
        result, calls = self.run_store(SLOW='1', SHORT_TIMEOUT='1')
        self.assertEqual(result.returncode, 124)
        self.assertEqual(self.transactions(calls), [])

    def test_preview_uses_local_metadata_and_read_only_brew_query(self):
        directory = self.home / 'preview'
        directory.mkdir()
        (directory / 'rows.json').write_text(json.dumps([
            store.row('owner/tap/beta', details='Formula details', installed=True)]))
        result = subprocess.run([sys.executable, str(ROOT / 'package_store.py'), '--preview',
                                 'brew', str(directory), '0'], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Status: Installed', result.stdout)
        self.assertIn('Version: 1.0', result.stdout)
        calls = [json.loads(line) for line in (self.home / 'calls').read_text().splitlines()]
        self.assertEqual(self.transactions(calls), [])
        self.assertIn(['info', '--formula', 'owner/tap/beta'], [args for name, args, _ in calls if name == 'brew'])

    def test_missing_dependencies_stop_before_picker(self):
        for provider in ('brew', 'mise'):
            for missing in (provider, 'fzf', 'timeout'):
                with self.subTest(provider=provider, missing=missing), \
                        patch.object(store.shutil, 'which', side_effect=lambda name: None if name == missing else '/bin/command'), \
                        patch.object(store, 'pick') as picker:
                    with self.assertRaisesRegex(store.StoreError, 'Missing dependency: ' + missing):
                        store.run(provider, 'install')
                    picker.assert_not_called()

    def test_missing_python_in_launchers_shows_guidance(self):
        for provider in ('brew', 'mise'):
            with self.subTest(provider=provider):
                result = subprocess.run(['/bin/bash', str(ROOT / (provider + '-store'))],
                                        env={**self.env, 'PATH': str(self.bin)},
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn('omarchy pkg add python', result.stderr)

    def test_cancel_does_not_wait_for_enter(self):
        with patch.object(sys, 'argv', ['package_store.py', 'brew']), patch.object(store, 'pick', return_value=None), \
                patch.object(store.shutil, 'which', return_value='/bin/command'), \
                patch.object(sys.stdin, 'isatty', return_value=True), patch.object(sys.stdout, 'isatty', return_value=True), \
                patch('builtins.input') as prompt:
            self.assertEqual(store.main(), 0)
            prompt.assert_not_called()

    def test_metadata_cannot_become_command_arguments(self):
        with patch.object(store, 'query_json', return_value={'formulae': []}), patch.object(store, 'query', return_value='--force\n'):
            with self.assertRaises(store.StoreError):
                store.brew_catalog('install')
        with patch.object(store, 'mise_installed', return_value={}), patch.object(store, 'query', return_value='$(touch injected)\n'):
            with self.assertRaises(store.StoreError):
                store.mise_catalog('install', 'versions', 'node')
        self.assertEqual(store.clean('name\tbad\n\x1b[31m'), 'name bad  [31m')


if __name__ == '__main__':
    unittest.main()
