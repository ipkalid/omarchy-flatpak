#!/usr/bin/env python3
"""Brew and mise adapters plus their shared, cancellable terminal picker."""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile

SCRIPT = str(Path(__file__).resolve())


class StoreError(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def clean(value):
    # Metadata is display-only. Remove terminal controls and row delimiters.
    return re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', str(value or ''))


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+/:@=~-]*', value):
        raise StoreError('The package manager returned an invalid package identifier.')
    return value


def query(argv, timeout=45):
    env = {**os.environ, 'HOMEBREW_NO_AUTO_UPDATE': '1', 'HOMEBREW_NO_ANALYTICS': '1'}
    result = subprocess.run(['timeout', '--foreground', '--kill-after=2s', str(timeout) + 's', *argv],
                            capture_output=True, text=True, env=env)
    if result.returncode:
        raise StoreError(f'{shlex.join(argv)} failed (exit {result.returncode}).\n'
                         + clean(result.stderr or 'Check your connection and package manager.'), result.returncode)
    return result.stdout


def query_json(argv):
    try:
        return json.loads(query(argv))
    except json.JSONDecodeError as error:
        raise StoreError('The package manager returned invalid JSON.') from error


def row(key, name=None, description='', details='', installed=False):
    return dict(key=identifier(key), name=clean(name or key), description=clean(description),
                details=details, installed=installed)


def brew_catalog(action):
    installed = query_json(['brew', 'info', '--json=v2', '--installed'])['formulae']
    by_name = {item.get('full_name', item['name']): item for item in installed}
    if action == 'remove':
        names = list(by_name)
    else:
        names = query(['brew', 'formulae']).splitlines()
    rows = []
    for name in sorted(set(names), key=str.casefold):
        item = by_name.get(name, {})
        versions = ', '.join(v['version'] for v in item.get('installed', []))
        rows.append(row(name, description=item.get('desc', ''), installed=name in by_name,
                        details=f'Formula: {clean(name)}\nInstalled versions: {clean(versions) or "None"}'))
    return rows


def mise_installed():
    data = query_json(['mise', 'ls', '--installed', '--json'])
    return {identifier(name): [v for v in versions if v.get('installed') is True]
            for name, versions in data.items() if any(v.get('installed') is True for v in versions)}


def mise_catalog(action, stage, tool):
    installed = mise_installed()
    if stage == 'tools':
        if action == 'remove':
            return [row(name, description=', '.join(v['version'] for v in versions), installed=True,
                        details='Installed versions: ' + ', '.join(clean(v['version']) for v in versions))
                    for name, versions in sorted(installed.items())]
        registry = query_json(['mise', 'registry', '--json'])
        return [row(item['short'], description=item.get('description', ''),
                    details='Backends: ' + ', '.join(clean(b) for b in item['backends']),
                    installed=item['short'] in installed)
                for item in sorted(registry, key=lambda item: item['short'].casefold())]
    tool = identifier(tool)
    versions = {identifier(v['version']): v for v in installed.get(tool, [])}
    available = list(versions) if action == 'remove' else query(['mise', 'ls-remote', tool]).splitlines()
    # Reverse mise's version order, retaining its backend-specific ordering
    # rather than sorting version strings lexicographically (e.g. 9 versus 10).
    rows = [row(tool + '@' + identifier(version), name=version,
                description=tool + (' · active' if versions.get(version, {}).get('active') else ''),
                installed=version in versions,
                details=f'Tool: {clean(tool)}\nVersion: {clean(version)}\n'
                        + ('Configured versions will remain in mise configuration after removal.'
                           if action == 'remove' else 'Install only; global and project defaults stay unchanged.'))
            for version in reversed(dict.fromkeys(available))]
    if action == 'install':
        latest = row(tool + '@latest', name='Latest', description=tool + ' · latest available version',
                     details=f'Tool: {clean(tool)}\nVersion: latest\n'
                             'mise resolves the latest eligible version when installation starts.\n'
                             'Install only; global and project defaults stay unchanged.')
        latest['status'] = 'Resolved when installing'
        rows.insert(0, latest)
    return rows


def load_catalog(provider, action, stage, tool, directory):
    directory = Path(directory)
    code = 0
    try:
        rows = brew_catalog(action) if provider == 'brew' else mise_catalog(action, stage, tool)
        (directory / 'rows.json').write_text(json.dumps(rows))
        if not rows:
            (directory / 'error').write_text('No installed packages or versions to remove.' if action == 'remove'
                                           else 'No packages or versions are available. Check the package manager and try again.')
            (directory / 'loaded-action').write_text('abort\n')
        else:
            (directory / 'loaded-action').write_text('change-header()\n')
        (directory / 'status').write_text('0')
        for index, item in enumerate(rows):
            marker = '  ✓' if item['installed'] else ''
            print(f"{index}\t{item['name'] + marker:<28}\t\033[2m{item['description']}\033[0m")
    except (StoreError, KeyError, TypeError, ValueError, AttributeError, OSError) as error:
        code = error.code if isinstance(error, StoreError) else 1
        (directory / 'error').write_text(str(error))
        (directory / 'status').write_text(str(code))
    return code


def stop_process_group(process):
    # Also terminate descendants if the worker already exited (e.g. a timeout).
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def pick(provider, action, stage='tools', tool='', multi=False):
    with tempfile.TemporaryDirectory(prefix='package-store-') as temporary:
        directory = Path(temporary)
        (directory / 'loaded-action').write_text('abort\n')
        worker = subprocess.Popen([sys.executable, SCRIPT, '--catalog', provider, action, stage, tool, temporary],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        picker = None
        try:
            preview = shlex.join([sys.executable, SCRIPT, '--preview', provider, temporary]) + ' {1}'
            loaded = 'load:transform:cat ' + shlex.quote(str(directory / 'loaded-action'))
            argv = ['fzf', '--ansi', '--delimiter=\t', '--with-nth=2,3', '--nth=1', '--no-hscroll',
                    '--prompt=> ', '--header=' + provider + ' · ' + action + (' · ' + tool if tool else ''),
                    '--bind=' + loaded, '--preview', preview,
                    '--preview-label=alt-p: details, alt-j/k: scroll' + (', tab: multi-select' if multi else ''),
                    '--preview-label-pos=bottom', '--preview-window=down:65%:wrap',
                    '--bind=alt-p:toggle-preview,alt-j:preview-down,alt-k:preview-up,alt-d:preview-half-page-down,alt-u:preview-half-page-up',
                    '--color=pointer:red,marker:red' if action == 'remove' else '--color=pointer:green,marker:green']
            if multi:
                argv.append('--multi')
            picker = subprocess.Popen(argv, stdin=worker.stdout, stdout=subprocess.PIPE, text=True,
                                      env={**os.environ, 'FZF_DEFAULT_OPTS': '', 'FZF_DEFAULT_OPTS_FILE': ''})
            worker.stdout.close()
            selected, _ = picker.communicate()
            if picker.returncode == 0 and selected:
                worker.wait()
            if (directory / 'status').exists():
                code = int((directory / 'status').read_text())
                if code:
                    raise StoreError((directory / 'error').read_text(), code)
                if (directory / 'error').exists():
                    print((directory / 'error').read_text())
                    return []
            if picker.returncode in (1, 130):
                return None
            if picker.returncode != 0:
                raise StoreError('The package picker failed.', picker.returncode)
            if not selected:
                return None
            if not (directory / 'status').exists():
                raise StoreError('The catalog did not finish loading. No packages were changed.')
            rows = json.loads((directory / 'rows.json').read_text())
            indices = list(dict.fromkeys(line.split('\t')[0] for line in selected.splitlines()))
            if (not multi and len(indices) != 1) or any(not i.isdecimal() or int(i) >= len(rows) for i in indices):
                raise StoreError('Invalid selection; no packages were changed.')
            return [rows[int(index)]['key'] for index in indices]
        finally:
            if picker is not None and picker.poll() is None:
                picker.terminate()
                picker.wait()
            stop_process_group(worker)
            worker.stderr.close()
            if worker.stdout and not worker.stdout.closed:
                worker.stdout.close()


def preview(provider, directory, index):
    if not index.isdecimal():
        return 2
    rows = json.loads((Path(directory) / 'rows.json').read_text())
    item = rows[int(index)]
    status = item.get('status', 'Installed' if item['installed'] else 'Not installed')
    print(f"Name: {item['name']}\nStatus: {status}")
    print(item['description'])
    print(item['details'])
    if provider == 'brew':
        try:
            print('\n'.join(clean(line) for line in query(['brew', 'info', '--formula', identifier(item['key'])], timeout=15).splitlines()))
        except StoreError:
            print('Additional details are unavailable.')
    return 0


def transact(argv):
    result = subprocess.run(argv)
    if result.returncode:
        raise StoreError(f'{argv[0]} did not complete successfully (exit {result.returncode}). See the details above.',
                         result.returncode if result.returncode > 0 else 128 - result.returncode)


def run(provider, action):
    if provider not in ('brew', 'mise') or action not in ('install', 'remove', 'update') or (provider == 'mise' and action == 'update'):
        raise StoreError('Unsupported provider or action.', 2)
    for dependency in (provider,) + (() if action == 'update' else ('timeout', 'fzf')):
        if not shutil.which(dependency):
            guidance = 'Install Homebrew using https://brew.sh and ensure brew is on PATH.' if dependency == 'brew' else 'Install it in a terminal with: omarchy pkg add ' + ('coreutils' if dependency == 'timeout' else dependency)
            raise StoreError(f'Missing dependency: {dependency}.\n{guidance}')
    if provider == 'mise':
        os.chdir(Path.home())
    if action == 'update':
        transact(['brew', 'update'])
        transact(['brew', 'upgrade', '--formula'])
    else:
        selected = pick(provider, action, multi=provider == 'brew')
        if not selected:
            return selected is not None
        if provider == 'mise':
            selected = pick(provider, action, stage='versions', tool=selected[0], multi=action == 'remove')
            if not selected:
                return selected is not None
        if action == 'remove':
            print('Remove these ' + ('tool versions' if provider == 'mise' else 'formulae') + '?')
            for name in selected:
                print('  ' + name)
            if provider == 'mise':
                print('mise configuration stays unchanged, including references to these versions.')
            if input('Continue? [y/N] ').strip().lower() not in ('y', 'yes'):
                return False
        operation = 'install' if action == 'install' else 'uninstall'
        transact([provider, operation, *(['--formula'] if provider == 'brew' else []), *selected])
    print(f'\n{provider} finished.')
    return True


def main():
    args = sys.argv[1:]
    internal = bool(args and args[0].startswith('--') and args[0] not in ('--help', '-h'))
    pause = not internal
    try:
        if args and args[0] == '--catalog' and len(args) == 6:
            return load_catalog(*args[1:])
        if args and args[0] == '--preview' and len(args) == 4:
            return preview(*args[1:])
        if args in (['--help'], ['-h']) or (len(args) == 2 and args[0] in ('brew', 'mise') and args[1] in ('--help', '-h')):
            pause = False
            print('Usage: package_store.py {brew|mise} [install|remove|update]\nmise supports install and remove only.')
            return 0
        if len(args) not in (1, 2):
            raise StoreError('Usage: package_store.py {brew|mise} [install|remove|update]', 2)
        pause = run(args[0], args[1] if len(args) == 2 else 'install')
        return 0
    except SystemExit:
        pause = False
        raise
    except (KeyboardInterrupt, EOFError):
        pause = False
        return 130
    except (StoreError, OSError, ValueError, KeyError, TypeError, IndexError) as error:
        print(str(error), file=sys.stderr)
        return error.code if isinstance(error, StoreError) else 1
    finally:
        if pause and sys.stdin.isatty() and sys.stdout.isatty():
            try:
                input('\nPress Enter to close… ')
            except (KeyboardInterrupt, EOFError):
                pass


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    signal.signal(signal.SIGHUP, lambda *_: sys.exit(129))
    raise SystemExit(main())
