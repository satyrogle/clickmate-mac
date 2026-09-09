# Continue ClickMate on Anu's Mac

The user asked to move this project online so Codex installed on Anu's Mac can
test and finish the Mac version directly. Continue implementation and testing
in this repository. Do not restart the Windows VM setup or rebuild the rejected
browser extension.

## Exact required sequence

For each queued work order:
1. Click the calibrated search field.
2. Command+A and Command+V the current ID.
3. Replay the recorded flow at its first Enter.
4. The recorded second action clicks the nested result link.
5. Continue the rest of the recorded ticket workflow.
6. Wait for return to the list, then handle the next ID.

Do not inject an extra Enter or a separate result click ahead of the recording.
The user explicitly corrected that error in the Windows implementation.

## Current files

- mac/clickmate.py: Tk interface, input listeners, recorder callbacks, worker,
  queue/text editors, Clear Flow, selected deletion and Mac permission help.
- mac/engine.py: pure queue/recording/playback logic and atomic persistence.
- mac/mac_input.py: pynput Mac controller, Command shortcuts, native clipboard
  via pbcopy/pbpaste, Quartz display layout, HIServices permission check.
- mac/OPEN ClickMate.command: launcher; user-local venv; pinned pynput; no Xcode.
- mac/starter-data.json: private 105-ID and one-comment snapshot from Windows.
- mac/test_engine.py and mac/test_recorder_events.py: 12 passing tests on Windows.

## What has not been proven

No actual Mac was connected during implementation. Python syntax, Bash syntax,
queue/recorder tests and Tk construction were checked on Windows. Do not call the
Mac input adapter or live TRIRIGA automation tested until you observe them here.

## Next work on the Mac

1. Inspect the installed macOS version, CPU architecture, Python/Tk and the
   project's state. Preserve any user changes and local flow.json.
2. Use the launcher; if Python is missing, use python.org's universal2 installer.
   Don't install a VM, Xcode or browser automation stack as a workaround.
3. Run the tests. Check which process macOS wants in Accessibility/Input
   Monitoring, and guide the user through any permission step they must perform.
   Running from Codex may attribute permissions differently from Terminal.
4. Test real recording and playback against a harmless local text field and
   button, including Command+V, Enter, mouse clicks, stop shortcut, multiline
   text and display coordinate scaling. Fix observed macOS issues in this repo.
5. Log in to TRIRIGA interactively. Record once on this Mac; Windows coordinates
   are intentionally absent. Calibrate the search field on the live screen.
6. Check the user's current remaining queue: the 105-ID snapshot might be stale.
   The example ticket completed while recording is not automatically removed.
7. Test one ticket under observation and verify TRIRIGA's state; proceed to a
   two-ticket transition test. Do not launch all 105 tickets as a smoke test.

The app uses recorded delays plus configurable extra wait; it does not inspect
TRIRIGA readiness or prove a ticket was completed. Queue advancement means the
recorded actions finished. An interrupted ID stays pending; inspect its actual
state before replaying. All Mac input controls this laptop's desktop, not the
Windows computer. Keep TRIRIGA foreground and the Mac awake/unlocked.

The user values a simple recorder that remembers text and a usable Clear Flow
control. Avoid adding setup complexity. Keep disk use small and remove only
generated test/build outputs created for this task.

Keep real IDs/comments and the release ZIP private. Authentication credentials
were not transferred. Don't record or store passwords in the flow.
