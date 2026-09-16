#!/usr/bin/env python3
"""Validate with Quickshell's virtual qs import mapped outside the plugin folder."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parent
shell = Path(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy')) / 'shell'
lint = shutil.which('qmllint') or '/usr/lib/qt6/bin/qmllint'
if not shell.is_dir() or not Path(lint).is_file():
    raise SystemExit('Install Omarchy and Qt qmllint before running this check.')
with tempfile.TemporaryDirectory(prefix='flatpak-qml-') as temporary:
    # Quickshell resolves qs.* virtually at runtime. Plain qmllint needs a
    # matching import root; this temporary symlink never enters the plugin.
    (Path(temporary) / 'qs').symlink_to(shell, target_is_directory=True)
    result = subprocess.run([lint, '-I', temporary, str(root / 'Panel.qml'), str(root / 'CenteredPanel.qml'), str(root / 'AsyncCommand.qml')], capture_output=True, text=True)
    if result.stdout or result.stderr:
        print(result.stdout + result.stderr, end='')
    if result.returncode or result.stderr.strip():
        raise SystemExit(result.returncode or 1)
print('QML validation passed.')
