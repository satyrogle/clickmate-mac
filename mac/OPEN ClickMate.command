#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export LANG=en_US.UTF-8
export PYTHONDONTWRITEBYTECODE=1
export PIP_DISABLE_PIP_VERSION_CHECK=1

fail() {
    printf '\n%s\n' "$1"
    read -r -p 'Press Return to close. ' unused || true
    exit 1
}
[[ "$(uname -s)" == Darwin ]] || fail 'This is the Mac package. Use CLICKMATE.exe on Windows.'

# Do not invoke the Apple Python shim: it can request a large developer-tools install.
python_bin=''
for candidate in \
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
    /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if [[ -x "$candidate" ]] && "$candidate" -c 'import sys, tkinter; assert (3,11) <= sys.version_info[:2] < (3,15)' >/dev/null 2>&1; then
        python_bin="$candidate"
        break
    fi
done
if [[ -z "$python_bin" ]]; then
    /usr/bin/open 'https://www.python.org/downloads/macos/'
    fail 'Install a Python 3.11–3.14 macOS universal2 installer from python.org, then double-click OPEN ClickMate again. Both Apple Silicon and Intel are supported by that installer.'
fi

runtime="$HOME/Library/Application Support/ClickMate Mac/runtime"
if [[ ! -x "$runtime/bin/python3" ]]; then
    printf 'Preparing ClickMate (first launch only)...\n'
    "$python_bin" -m venv "$runtime" || fail 'Could not create the small ClickMate runtime.'
fi
if ! "$runtime/bin/python3" -c 'import importlib.metadata as m; assert m.version("pynput") == "1.8.2"; import tkinter, Quartz, HIServices' >/dev/null 2>&1; then
    "$runtime/bin/python3" -m pip install --only-binary=:all: --no-cache-dir -r requirements.txt || \
        fail 'Dependency setup failed. Check the internet connection and use the python.org universal2 installer. No Xcode or VM is required.'
fi

printf 'Opening ClickMate. Keep this Terminal window open while it runs.\n'
printf 'First launch: allow Terminal/Python in Accessibility and Input Monitoring, then reopen.\n'
"$runtime/bin/python3" clickmate.py || fail 'ClickMate reported an error above. Copy that message for troubleshooting.'
