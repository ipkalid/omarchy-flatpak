#!/usr/bin/env python3
"""Inspect, set up, or clean up this plugin's Omarchy menu shortcuts."""
import argparse
import datetime
import json
from pathlib import Path
import shlex
import shutil

from install import TRAILING, atomic_write, merge_menu, parse_jsonc


def entry_spans(raw):
    _, clean = parse_jsonc(raw)
    clean = TRAILING.sub(lambda m: m[0] if m[0].startswith('"') else ' ' + m[0][1:], clean)
    decoder = json.JSONDecoder()
    spans = []
    pos = clean.index('{') + 1
    while True:
        while clean[pos].isspace() or clean[pos] == ',':
            pos += 1
        if clean[pos] == '}':
            return clean, spans
        start = pos
        key, pos = decoder.raw_decode(clean, pos)
        while clean[pos].isspace() or clean[pos] == ':':
            pos += 1
        value_start = pos
        _, pos = decoder.raw_decode(clean, pos)
        if any(span[0] == key for span in spans):
            raise ValueError(f'Duplicate menu key: {key}')
        spans.append((key, start, value_start, pos))


def edit_entry(raw, key, value=None):
    clean, spans = entry_spans(raw)
    for index, (name, start, value_start, end) in enumerate(spans):
        if name != key:
            continue
        if value is not None:
            replacement = json.dumps(value, ensure_ascii=False, indent=2).replace('\n', '\n  ')
            return raw[:value_start] + replacement + raw[end:]
        edits = [(start, end)]
        following = end
        while clean[following].isspace():
            following += 1
        if clean[following] == ',':
            edits.append((following, following + 1))
        elif index:
            comma = clean.index(',', spans[index - 1][3], start)
            edits.append((comma, comma + 1))
        else:
            # A sole entry can still have an original JSONC trailing comma.
            _, commented = parse_jsonc(raw)
            comma = commented.find(',', end, commented.rfind('}'))
            if comma >= 0:
                edits.append((comma, comma + 1))
        for begin, finish in sorted(edits, reverse=True):
            raw = raw[:begin] + raw[finish:]
        parse_jsonc(raw)
        return raw
    return raw


def entries_for(plugin_id):
    command = 'omarchy-shell shell summon ' + shlex.quote(plugin_id)
    entries = {}
    for action in ('install', 'remove', 'update'):
        payload = shlex.quote(json.dumps({'action': action}, separators=(',', ':')))
        entries[action + '.flatpak'] = {'icon': '󰏖', 'label': 'Flatpak', 'action': command + ' ' + payload}
    return entries


def old_panel_entry(plugin_id):
    return {'icon': '󰏖', 'label': 'Flatpak Store',
            'action': 'omarchy-shell shell summon ' + shlex.quote(plugin_id) + " '{}'"}


def legacy_entries(home):
    command = 'xdg-terminal-exec --app-id=org.omarchy.terminal ' + shlex.quote(str(home / '.local/bin/flatpak-store'))
    return {action + '.flatpak': {'icon': '󰏖', 'label': 'Flatpak',
                                 'action': command + (' remove' if action == 'remove' else '')}
            for action in ('install', 'remove')}


def status(raw, plugin_id, home):
    data, _ = parse_jsonc(raw)
    entry_spans(raw)  # Refuse ambiguous duplicate keys before any changes.
    legacy = legacy_entries(home)
    missing, conflicts = [], []
    for key, entry in entries_for(plugin_id).items():
        if key not in data or (key in legacy and data[key] == legacy[key]):
            missing.append(key)
        elif data[key] != entry:
            conflicts.append(key)
    old_panel = data.get('flatpak-store') == old_panel_entry(plugin_id)
    return {'ok': True, 'status': 'conflict' if conflicts else
            'missing' if missing or old_panel else 'complete',
            'missing': missing, 'conflicts': conflicts, 'legacyPanel': old_panel}


def configure(raw, plugin_id, home, cleanup=False):
    state = status(raw, plugin_id, home)
    if not cleanup and state['conflicts']:
        raise ValueError(', '.join(state['conflicts']) +
                         ' already exists with different settings; no files were changed')
    data, _ = parse_jsonc(raw)
    for key, entry in entries_for(plugin_id).items():
        if cleanup:
            if data.get(key) == entry:
                raw = edit_entry(raw, key)
        elif key in data:
            if data[key] != entry:
                raw = edit_entry(raw, key, entry)
        else:
            raw = merge_menu(raw, entry, key)
    # This former root entry is obsolete. Preserve user-customized versions.
    if state['legacyPanel']:
        raw = edit_entry(raw, 'flatpak-store')
    parse_jsonc(raw)
    return raw


def run(args):
    manifest = json.loads(Path(__file__).with_name('manifest.json').read_text())
    plugin_id = manifest['id']
    home = args.home.expanduser().resolve()
    menu = home / '.config/omarchy/extensions/omarchy-menu.jsonc'
    raw = menu.read_text() if menu.exists() else '{}\n'
    if args.action == 'status':
        return {**status(raw, plugin_id, home), 'menu': str(menu)}
    result = configure(raw, plugin_id, home, args.action == 'cleanup')
    response = {**status(result, plugin_id, home), 'changed': raw != result,
                'menu': str(menu), 'backup': None, 'dryRun': args.dry_run}
    if args.dry_run:
        return {**response, 'content': result}
    if raw != result:
        if menu.exists():
            backup = menu.with_name(menu.name + '.bak.' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            shutil.copy2(menu, backup)
            response['backup'] = str(backup)
        atomic_write(menu, result.encode(), (menu.stat().st_mode & 0o777) if menu.exists() else 0o644)
    return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'setup', 'cleanup'))
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--json', action='store_true', help='Print one structured JSON result')
    args = parser.parse_args()
    try:
        result = run(args)
    except (ValueError, OSError, KeyError) as error:
        result = {'ok': False, 'error': str(error)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif not result['ok']:
        print('Menu ' + args.action + ' failed: ' + result['error'])
    elif args.dry_run and 'content' in result:
        print(result['content'])
    else:
        print('Menu: ' + result['menu'])
        if result.get('backup'):
            print('Backup: ' + result['backup'])
        print('Menu shortcuts: ' + result['status'])
        if result.get('changed'):
            print('Menu updated. Omarchy reloads it automatically.')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
