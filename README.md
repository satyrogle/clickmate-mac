# ClickMate Mac

Private transfer repository for testing the Mac version on Anu's laptop.

The app pastes each work-order ID into the calibrated TRIRIGA search field, then
replays the recorded flow starting with **Enter**, followed by the nested result
link and remaining ticket steps. It remembers typed/pasted text and supports a
queue, Test Next, Run Batch, Clear Flow, selected-step deletion and editable waits.

## Open on the Mac

Download the ZIP from Releases and unzip it, then double-click
`OPEN ClickMate.command`. Alternatively clone this repo and launch
`mac/OPEN ClickMate.command`.

The launcher detects Python 3.11–3.14 with Tk. If none is available, it opens
python.org for a macOS universal2 installer. It installs `pynput==1.8.2` and its
macOS dependencies into a local environment on first run. It does not install
Xcode, a Windows VM, or a browser extension.

Allow the launching app (normally Terminal, or Python as shown by macOS) in
Accessibility and Input Monitoring. Reopen after granting permissions. Actual
macOS permissions and input playback have not yet been tested on a Mac.

## Continue in Codex

Read `MAC-HANDOFF.md`, inspect the Mac environment, run the included tests, and
test the real input adapter locally before attempting TRIRIGA playback.

## Data and privacy

**Keep this repository private.** `mac/starter-data.json` and the private release
ZIP include a snapshot of 105 real work-order IDs and one reusable comment from
the Windows app. It contains no transferred Windows click coordinates. This is
not a live sync: verify the queue before using it. Do not publish the starter data
or release asset in a public repository.

Record the click positions once on this Mac and set its search field. During
playback, use the Windows computer for other work; ClickMate controls the Mac's
own mouse, keyboard and clipboard.

Local state is saved in `~/Library/Application Support/ClickMate Mac/flow.json`.
The starter data is used only when that local file does not exist.

## Validation so far

- 12 logic/recorder event tests passed on Windows, including ID→Enter→link order,
  stopping without skipping the next ID, saved text, clearing a flow, and progress.
- Python and launcher syntax checked; Tk UI construction checked on Windows.
- ZIP integrity, Unix executable permissions and LF launcher checked.
- Native Mac input, permissions and live TRIRIGA playback remain unverified.

Run `python3 -m unittest discover -s mac -p 'test_*.py' -v` from this repository.
