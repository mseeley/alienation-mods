#!/usr/bin/env python3
"""Build "Alienation Savegame Editor.app" (macOS) so the save editor opens with a double-click.

  tools/.venv/bin/python tools/make-save-editor-app.py

The bundle is written next to this script (tools/). Its launcher runs tools/save-editor-gui.py
with tools/.venv and logs to tools/.cache/save-editor-gui.log. It finds tools/ from its own
location, falling back to the path it was built in, so it can also be copied to /Applications
or dragged to the Dock. Rebuild it if the project folder moves.
"""
import os
import plistlib
import shutil
import stat
import struct
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
NAME = 'Alienation Savegame Editor'
APP = os.path.join(TOOLS, f'{NAME}.app')

LAUNCHER = r'''#!/bin/bash
# Launches the Alienation Savegame Editor (tools/save-editor-gui.py) with the project's venv.
# Built by tools/make-save-editor-app.py.
HERE="$(cd "$(dirname "$0")/../../.." && pwd)"
if [ -f "$HERE/save-editor-gui.py" ]; then TOOLS="$HERE"; else TOOLS="@TOOLS@"; fi
PY="$TOOLS/.venv/bin/python"
LOG="$TOOLS/.cache/save-editor-gui.log"

alert() {
    /usr/bin/osascript - "$1" <<'APPLESCRIPT' >/dev/null 2>&1
on run argv
    display alert "Alienation Savegame Editor" message (item 1 of argv) as critical
end run
APPLESCRIPT
}

if [ ! -f "$TOOLS/save-editor-gui.py" ]; then
    alert "Cannot find the save editor at $TOOLS. Rebuild the app with tools/make-save-editor-app.py."
    exit 1
fi
if [ ! -x "$PY" ]; then
    alert "No Python environment at $TOOLS/.venv. In Terminal, from the project folder, run:

python3 -m venv tools/.venv && tools/.venv/bin/pip install -r tools/requirements.txt"
    exit 1
fi
mkdir -p "$TOOLS/.cache"
cd "$TOOLS/.."
args=()
for a in "$@"; do case "$a" in -psn_*) ;; *) args+=("$a") ;; esac; done
"$PY" "$TOOLS/save-editor-gui.py" "${args[@]}" >"$LOG" 2>&1
status=$?
if [ $status -ne 0 ]; then
    alert "The save editor stopped with an error (exit $status). Details:

$(tail -n 12 "$LOG")

Full log: $LOG"
fi
exit $status
'''


# .icns entries holding PNG data: (type, pixel size). Written directly, so iconutil isn't needed.
ICNS_TYPES = [(b'icp4', 16), (b'icp5', 32), (b'ic11', 32), (b'ic12', 64), (b'ic07', 128), (b'ic13', 256),
              (b'ic08', 256), (b'ic14', 512), (b'ic09', 512), (b'ic10', 1024)]


def build_icns(dest):
    """Render the editor's icon at every size macOS uses and pack them into an .icns file."""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    sys.path.insert(0, TOOLS)
    import importlib
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    gui = importlib.import_module('save-editor-gui')
    chunks = []
    for kind, size in ICNS_TYPES:
        data = QtCore.QByteArray()
        buf = QtCore.QBuffer(data)
        buf.open(QtCore.QIODevice.WriteOnly)
        gui.app_icon_pixmap(size).save(buf, 'PNG')
        png = bytes(data)
        chunks.append(kind + struct.pack('>I', 8 + len(png)) + png)
    body = b''.join(chunks)
    with open(dest, 'wb') as f:
        f.write(b'icns' + struct.pack('>I', 8 + len(body)) + body)
    del app


def main():
    if sys.platform != 'darwin':
        sys.exit('This builds a macOS app bundle; on other systems run tools/save-editor-gui.py directly.')
    if os.path.exists(APP):
        shutil.rmtree(APP)
    contents = os.path.join(APP, 'Contents')
    os.makedirs(os.path.join(contents, 'MacOS'))
    os.makedirs(os.path.join(contents, 'Resources'))
    exe = os.path.join(contents, 'MacOS', 'save-editor')
    with open(exe, 'w') as f:
        f.write(LAUNCHER.replace('@TOOLS@', TOOLS))
    os.chmod(exe, os.stat(exe).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    with open(os.path.join(contents, 'Info.plist'), 'wb') as f:
        plistlib.dump({
            'CFBundleName': NAME, 'CFBundleDisplayName': NAME,
            'CFBundleIdentifier': 'local.alienation.savegame-editor',
            'CFBundleExecutable': 'save-editor', 'CFBundleIconFile': 'AppIcon',
            'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': '1.0', 'CFBundleVersion': '1',
            'LSMinimumSystemVersion': '11.0', 'NSHighResolutionCapable': True,
        }, f)
    build_icns(os.path.join(contents, 'Resources', 'AppIcon.icns'))
    print(f'built {APP}')


if __name__ == '__main__':
    main()
