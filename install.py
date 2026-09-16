#!/usr/bin/env python3
"""Install the launcher and merge its menu entries without removing JSONC comments."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import tempfile

KEY = "install.flatpak"
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/')
TRAILING = re.compile(r'"(?:\\.|[^"\\])*"|,\s*(?=[}\]])')


def parse_jsonc(raw):
    # Keep character offsets intact so insertion preserves the original file.
    clean = TOKEN.sub(lambda m: m[0] if m[0].startswith('"') else
                      ''.join('\n' if c == '\n' else ' ' for c in m[0]), raw)
    normalized = TRAILING.sub(lambda m: m[0] if m[0].startswith('"') else
                              ' ' + m[0][1:], clean)
    data = json.loads(normalized)
    if not isinstance(data, dict):
        raise ValueError("Menu extension must be a JSON object")
    return data, clean


def merge_menu(raw, entry, key=KEY):
    data, clean = parse_jsonc(raw)
    if key in data:
        if data[key] != entry:
            raise ValueError(f"{key} already exists with different settings; review it before installing")
        return raw
    end = clean.rfind('}')
    # Add a separator immediately after the last value (before any comment).
    last = len(clean[:end].rstrip())
    separator = ',' if data and not clean[:last].endswith(',') else ''
    prefix = raw[:last] + separator + raw[last:end]
    addition = json.dumps({key: entry}, ensure_ascii=False, indent=2)[2:-2]
    merged = prefix.rstrip() + '\n' + addition + '\n' + raw[end:]
    parse_jsonc(merged)
    return merged


def atomic_write(path, content, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home(), help='Target home (also useful for staging)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    home = args.home.expanduser().resolve()
    launcher = home / '.local/bin/flatpak-store'
    menu = home / '.config/omarchy/extensions/omarchy-menu.jsonc'
    entry = {'icon': '󰏖', 'label': 'Flatpak',
             'action': 'xdg-terminal-exec --app-id=org.omarchy.terminal ' + shlex.quote(str(launcher))}
    entries = {KEY: entry, 'remove.flatpak': {**entry, 'action': entry['action'] + ' remove'}}
    raw = menu.read_text() if menu.exists() else '{}\n'
    merged = raw
    for key, menu_entry in entries.items():
        merged = merge_menu(merged, menu_entry, key)
    source = Path(__file__).with_name('flatpak-store').read_bytes()
    print(f'Launcher: {launcher}\nMenu: {menu}\nEntries: {json.dumps(entries, ensure_ascii=False)}')
    if args.dry_run:
        return
    if menu.exists() and merged != raw:
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup = menu.with_name(f'{menu.name}.bak.{stamp}')
        shutil.copy2(menu, backup)
        print(f'Backup: {backup}')
    atomic_write(launcher, source, 0o755)
    if merged != raw:
        atomic_write(menu, merged.encode(), (menu.stat().st_mode & 0o777) if menu.exists() else 0o644)
    print('Installed. Open Omarchy → Install → Flatpak or Remove → Flatpak.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(f'Installation failed: {error}')
