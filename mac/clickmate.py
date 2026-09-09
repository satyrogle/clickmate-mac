from __future__ import annotations

import copy
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from engine import Recording, Stopped, load_project, parse_ids, play, save_project

DATA = Path.home() / 'Library' / 'Application Support' / 'ClickMate Mac'
SAVE = DATA / 'flow.json'
SEED = Path(__file__).with_name('starter-data.json')


class ClickMate:
    def __init__(self, root):
        self.root = root
        self.project = load_project(SAVE, SEED)
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.mode = 'idle'
        self.hooks = []
        self.modifiers = set()
        self.mouse_down = {}
        self.recording = None
        self.pending = None
        self.buttons = []
        root.title('ClickMate Mac')
        root.geometry('1000x700')
        root.minsize(880, 600)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.report_callback_exception = lambda cls, value, tb: messagebox.showerror('ClickMate', str(value))

        outer = ttk.Frame(root, padding=14)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='ClickMate Mac', font=('Helvetica', 21, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='Paste work order → recorded Enter → nested links → repeat').pack(anchor='w', pady=(3, 12))
        bar = ttk.Frame(outer)
        bar.pack(fill='x')
        self.button(bar, 'RECORD', self.record)
        self.button(bar, 'SET SEARCH BAR', self.calibrate)
        self.button(bar, 'TEST NEXT', lambda: self.start_run(1))
        self.button(bar, 'RUN BATCH', lambda: self.start_run(None))
        ttk.Button(bar, text='STOP (Ctrl+Option+Esc)', command=self.stop).pack(side='left', padx=3)

        setup = ttk.Frame(outer)
        setup.pack(fill='x', pady=10)
        self.button(setup, 'PASTE ORDER IDS', self.edit_queue)
        self.button(setup, 'SAVED TEXT', self.edit_values)
        self.button(setup, 'CLEAR FLOW', self.clear_flow)
        self.button(setup, 'EXPORT', self.export)
        self.button(setup, 'IMPORT', self.import_flow)
        self.button(setup, 'MAC PERMISSIONS', self.permissions)
        self.summary = tk.StringVar()
        ttk.Label(outer, textvariable=self.summary).pack(anchor='w', pady=(0, 8))

        timing = ttk.Frame(outer)
        timing.pack(fill='x', pady=(0, 8))
        ttk.Label(timing, text='Extra wait before clicks (seconds):').pack(side='left')
        self.extra = tk.StringVar(value=str(self.project['extra_wait']))
        ttk.Entry(timing, textvariable=self.extra, width=5).pack(side='left', padx=(5, 20))
        ttk.Label(timing, text='Wait between work orders:').pack(side='left')
        self.reload = tk.StringVar(value=str(self.project['reload_wait']))
        ttk.Entry(timing, textvariable=self.reload, width=5).pack(side='left', padx=5)

        frame = ttk.Frame(outer)
        frame.pack(fill='both', expand=True)
        self.steps = ttk.Treeview(frame, columns=('delay', 'kind', 'detail'), show='headings', selectmode='extended')
        for key, label, width in [('delay', 'Wait (s)', 75), ('kind', 'Action', 90), ('detail', 'Recorded step / remembered text', 650)]:
            self.steps.heading(key, text=label)
            self.steps.column(key, width=width, stretch=(key == 'detail'))
        self.steps.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(frame, orient='vertical', command=self.steps.yview)
        scroll.pack(side='right', fill='y')
        self.steps.configure(yscrollcommand=scroll.set)
        self.steps.bind('<Double-1>', lambda _: self.edit_step())
        edits = ttk.Frame(outer)
        edits.pack(fill='x', pady=8)
        self.button(edits, 'EDIT STEP', self.edit_step)
        self.button(edits, 'CHANGE WAIT', self.edit_delay)
        self.button(edits, 'DELETE SELECTED', self.delete_steps)
        self.button(edits, 'HOW TO USE', self.help)

        self.status = tk.StringVar(value='Record once on this Mac. Your imported IDs and saved text are ready.')
        ttk.Label(outer, textvariable=self.status, wraplength=920).pack(anchor='w', pady=6)
        ttk.Label(outer, text='Stop anywhere: Control + Option + Escape (or Fn + F8). Keep TRIRIGA visible on this Mac.').pack(anchor='w')
        self.refresh()
        root.after(40, self.poll)

    def button(self, parent, label, command):
        button = ttk.Button(parent, text=label, command=command)
        button.pack(side='left', padx=3)
        self.buttons.append(button)

    def persist(self):
        save_project(SAVE, self.project)

    def refresh(self):
        self.steps.delete(*self.steps.get_children())
        for i, action in enumerate(self.project['actions']):
            kind = action['kind']
            detail = action.get('value', action.get('key', ''))
            if kind in ('click', 'drag', 'scroll'):
                detail = f"({action['x']}, {action['y']}) " + action.get('button', '')
            elif kind == 'combo':
                detail = '+'.join(action['keys'])
            self.steps.insert('', 'end', iid=str(i), values=(f"{action['delay']:.2f}", kind, detail))
        left = self.project['queue'][self.project['next_index']:]
        search = self.project['search']
        self.summary.set(f"{len(left)} IDs left | Next: {left[0] if left else 'none'} | "
                         f"{len(self.project['actions'])} steps | Search bar: {tuple(search) if search else 'not set'}")

    def set_mode(self, mode):
        self.mode = mode
        for button in self.buttons:
            button.configure(state='normal' if mode == 'idle' else 'disabled')

    def ensure_hooks(self):
        from mac_input import permissions_ready
        if not permissions_ready():
            self.permissions()
            return False
        if self.hooks and all(h.is_alive() for h in self.hooks):
            return True
        for hook in self.hooks:
            hook.stop()
        from pynput import keyboard, mouse
        self.hooks = [keyboard.Listener(on_press=self.key_press, on_release=self.key_release),
                      mouse.Listener(on_click=self.mouse_click, on_scroll=self.mouse_scroll)]
        for hook in self.hooks:
            hook.start()
        return True

    @staticmethod
    def modifier(key):
        name = str(key).replace('Key.', '')
        for value in ('cmd', 'ctrl', 'alt', 'shift'):
            if name in (value, value + '_l', value + '_r'):
                return value
        return None

    def key_press(self, key, injected=False):
        if injected:
            return
        mod = self.modifier(key)
        if mod:
            self.modifiers.add(mod)
            return
        name = str(key).replace('Key.', '')
        if name == 'f8' or (name == 'esc' and {'ctrl', 'alt'} <= self.modifiers):
            self.stop_event.set()
            self.events.put(('stop', time.monotonic()))
            return
        if self.mode != 'recording' or self.stop_event.is_set():
            return
        char = getattr(key, 'char', None)
        self.events.put(('key', time.monotonic(), name, char, sorted(self.modifiers)))

    def key_release(self, key, injected=False):
        if injected:
            return
        mod = self.modifier(key)
        if mod:
            self.modifiers.discard(mod)

    def mouse_click(self, x, y, button, pressed, injected=False):
        if injected:
            return
        if self.mode not in ('recording', 'calibrating') or self.stop_event.is_set():
            return
        self.events.put(('mouse', time.monotonic(), x, y, button.name, pressed))

    def mouse_scroll(self, x, y, dx, dy, injected=False):
        if injected:
            return
        if self.mode == 'recording' and not self.stop_event.is_set():
            self.events.put(('scroll', time.monotonic(), x, y, dx, dy))

    def poll(self):
        try:
            while True:
                self.consume(self.events.get_nowait())
        except queue.Empty:
            pass
        except Exception as error:
            self.stop()
            self.status.set(str(error))
            messagebox.showerror('ClickMate stopped', str(error))
        if self.mode in ('recording', 'calibrating', 'playing') and any(not h.is_alive() for h in self.hooks):
            self.stop()
            self.status.set('Mac input monitoring stopped. Check permissions, then reopen ClickMate.')
        self.root.after(40, self.poll)

    def consume(self, event):
        kind, at, *rest = event
        if kind == 'stop':
            self.stop(at)
        elif kind == 'status':
            self.status.set(rest[0])
        elif kind == 'done':
            self.project = rest[1]
            self.set_mode('idle')
            self.restore()
            self.refresh()
            self.status.set(rest[0])
        elif kind == 'mouse' and self.mode in ('recording', 'calibrating'):
            x, y, button, pressed = rest
            if self.mode == 'calibrating':
                if not pressed and button == 'left':
                    from mac_input import display_layout
                    self.project['search'] = [x, y]
                    self.project['search_displays'] = display_layout()
                    self.persist()
                    self.set_mode('idle')
                    self.restore()
                    self.refresh()
                    self.status.set('Search bar saved. The runner pastes each ID, then your Enter step starts.')
                return
            if not self.recording.actions:
                return  # Focus clicks before the first Enter aren't part of the flow.
            if button not in ('left', 'right', 'middle'):
                return
            if pressed:
                self.mouse_down[button] = (x, y, at)
            elif button in self.mouse_down:
                sx, sy, started = self.mouse_down.pop(button)
                action = dict(kind='click', x=sx, y=sy, button=button)
                if abs(x - sx) + abs(y - sy) > 5:
                    action.update(kind='drag', end_x=x, end_y=y, duration=at - started)
                self.recording.add(action, started, at)
        elif kind == 'scroll' and self.mode == 'recording':
            if not self.recording.actions:
                return
            x, y, dx, dy = rest
            self.recording.add(dict(kind='scroll', x=x, y=y, dx=dx, dy=dy), at)
        elif kind == 'key' and self.mode == 'recording':
            name, char, mods = rest
            if not self.recording.actions and (name != 'enter' or mods):
                return
            if char and any(m in mods for m in ('cmd', 'ctrl')):
                # macOS Command+V must remember the literal clipboard contents.
                normalized = chr(ord(char) + 96) if len(char) == 1 and 1 <= ord(char) <= 26 else char.lower()
                if normalized == 'v' and 'cmd' in mods:
                    from mac_input import clipboard_text
                    self.recording.add(dict(kind='text', value=clipboard_text()), at)
                else:
                    self.recording.add(dict(kind='combo', keys=mods + [normalized]), at)
            elif char and char.isprintable():
                self.recording.text(char, at)
            elif name == 'space':
                self.recording.text(' ', at)
            elif name in ('enter', 'tab', 'backspace', 'delete', 'esc', 'left', 'right', 'up', 'down', 'home', 'end', 'page_up', 'page_down'):
                action = dict(kind='combo', keys=mods + [name]) if mods else dict(kind='key', key=name)
                self.recording.add(action, at)

    def countdown(self, mode, action):
        if self.mode != 'idle' or not self.ensure_hooks():
            return
        self.stop_event.clear()
        self.set_mode('countdown')
        self.status.set('Starting in 4 seconds. Switch to TRIRIGA now.')
        self.root.iconify()
        def begin():
            self.pending = None
            if self.stop_event.is_set():
                return
            self.mouse_down.clear()
            self.set_mode(mode)
            action()
        self.pending = self.root.after(4000, begin)

    def record(self):
        if self.project['actions'] and not messagebox.askyesno('Record again', 'Replace the current recorded flow? Your IDs and saved text stay.'):
            return
        messagebox.showinfo('Record from Enter',
            'In TRIRIGA, put a sample work-order ID in the search bar first.\n\n'
            'Click OK, switch to TRIRIGA during the 4-second countdown, and start with Enter. '
            'Click its nested result link and perform the whole flow normally.\n\n'
            'Wait until TRIRIGA is back at the search screen, then press Control + Option + Escape. '
            'Do not record login or passwords. Remove that sample ID from the queue if you completed it while recording.')
        def begin():
            self.recording = Recording(time.monotonic())
            self.status.set('Ready: press Enter in TRIRIGA to begin the flow. Control + Option + Escape stops.')
        self.countdown('recording', begin)

    def calibrate(self):
        self.countdown('calibrating', lambda: self.status.set('Click inside the work-order search field ONCE.'))

    def stop(self, at=None):
        at = time.monotonic() if at is None else at
        self.stop_event.set()
        if self.pending:
            self.root.after_cancel(self.pending)
            self.pending = None
        if self.mode == 'playing':
            self.status.set('Stopping. Waiting for the current input to release...')
            return
        if self.mode == 'recording' and self.recording and self.recording.actions:
            from mac_input import display_layout
            actions = self.recording.finish(at, self.project['values'])
            self.project['actions'] = actions
            self.project['displays'] = display_layout()
            self.persist()
            self.status.set(f'Recorded {len(actions)} steps. Check that step 1 is Enter, then TEST NEXT.')
        else:
            self.status.set('Stopped.')
        self.recording = None
        self.set_mode('idle')
        self.restore()
        self.refresh()

    def restore(self):
        self.root.deiconify()
        self.root.lift()

    def start_run(self, limit):
        from mac_input import MacInput, display_layout
        if not self.project['actions'] or not self.project['search']:
            messagebox.showinfo('Set up the flow', 'Use RECORD and SET SEARCH BAR first.')
            return
        layout = display_layout()
        if self.project['displays'] != layout:
            messagebox.showerror('Display changed', 'Record again with the current Mac display layout before running.')
            return
        if self.project['search_displays'] != layout:
            messagebox.showerror('Search position changed', 'Use SET SEARCH BAR with the current Mac display layout.')
            return
        self.project['extra_wait'] = float(self.extra.get())
        self.project['reload_wait'] = float(self.reload.get())
        if not 0 <= self.project['extra_wait'] <= 120 or not 0 <= self.project['reload_wait'] <= 300:
            raise ValueError('Waits must be 0–120 seconds per click and 0–300 between orders.')
        self.persist()
        run_project = copy.deepcopy(self.project)
        def begin():
            def worker():
                # Keep this Mac awake only while the worker is running.
                awake = None
                try:
                    awake = subprocess.Popen(['/usr/bin/caffeinate', '-i'])
                    play(run_project, MacInput(), self.stop_event,
                         lambda s: self.events.put(('status', 0, s)),
                         lambda p: save_project(SAVE, p), limit)
                    result = 'Recorded flow finished. Check the resulting ticket status in TRIRIGA.'
                except Exception as error:
                    result = str(error)
                finally:
                    if awake:
                        try:
                            awake.terminate()
                            awake.wait(timeout=3)
                        except (OSError, subprocess.TimeoutExpired):
                            pass
                self.events.put(('done', 0, result, run_project))
            threading.Thread(target=worker, daemon=True).start()
        self.countdown('playing', begin)

    def text_dialog(self, title, initial, callback):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry('580x420')
        box = tk.Text(win, wrap='word', padx=8, pady=8)
        box.pack(fill='both', expand=True)
        box.insert('1.0', initial)
        def commit():
            callback(box.get('1.0', 'end-1c'))
            win.destroy()
        ttk.Button(win, text='SAVE', command=commit).pack(pady=8)
        win.transient(self.root)
        win.grab_set()
        box.focus_set()

    def edit_queue(self):
        def commit(text):
            ids = parse_ids(text)
            if len(ids) > 1000:
                raise ValueError('Use up to 1,000 IDs per list.')
            self.project['queue'], self.project['next_index'] = ids, 0
            self.persist()
            self.refresh()
        self.text_dialog('Work orders remaining — one per line',
                         '\n'.join(self.project['queue'][self.project['next_index']:]), commit)

    def edit_values(self):
        known = ', '.join(self.project['values']) or 'none yet'
        name = simpledialog.askstring('Saved text', 'Name (existing: ' + known + '):', initialvalue='comment')
        if not name:
            return
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name):
            raise ValueError('Use letters, digits or underscores for the name.')
        def commit(value):
            self.project['values'][name] = value
            self.persist()
            self.status.set('Saved. Text steps can use {{' + name + '}} wherever it is needed.')
        self.text_dialog('Saved text: ' + name, self.project['values'].get(name, ''), commit)

    def selected(self):
        rows = self.steps.selection()
        return int(rows[0]) if rows else None

    def edit_step(self):
        if self.mode != 'idle':
            return
        index = self.selected()
        if index is None:
            return
        action = self.project['actions'][index]
        if action['kind'] != 'text':
            self.edit_delay()
            return
        def commit(value):
            action['value'] = value
            self.persist()
            self.refresh()
        self.text_dialog('Remembered text — literal text or {{comment}}', action['value'], commit)

    def edit_delay(self):
        index = self.selected()
        if index is None:
            return
        action = self.project['actions'][index]
        value = simpledialog.askfloat('Wait before step', 'Seconds:', initialvalue=action['delay'], minvalue=0, maxvalue=300)
        if value is not None:
            action['delay'] = value
            self.persist()
            self.refresh()

    def delete_steps(self):
        for index in sorted(map(int, self.steps.selection()), reverse=True):
            del self.project['actions'][index]
        self.persist()
        self.refresh()

    def clear_flow(self):
        if messagebox.askyesno('Clear flow', 'Delete all recorded steps? Your queue and saved text stay.'):
            self.project['actions'] = []
            self.persist()
            self.refresh()

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension='.json', initialfile='ClickMate-backup.json')
        if path:
            save_project(Path(path), self.project)

    def import_flow(self):
        path = filedialog.askopenfilename(filetypes=[('ClickMate JSON', '*.json')])
        if path:
            project = load_project(Path(path), SEED)
            if messagebox.askyesno('Import flow', 'Replace this Mac queue, flow and saved text with the selected file?'):
                self.project = project
                self.extra.set(str(project['extra_wait']))
                self.reload.set(str(project['reload_wait']))
                self.persist()
                self.refresh()

    def permissions(self):
        messagebox.showinfo('Mac input permissions',
            'In System Settings → Privacy & Security, enable Accessibility and Input Monitoring for '
            'Terminal (or Python if macOS lists it). Then quit and reopen ClickMate.\n\n'
            'These allow recording clicks/keys and replaying them. Screen Recording permission is not needed.')
        subprocess.Popen(['/usr/bin/open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'])

    def help(self):
        messagebox.showinfo('ClickMate Mac',
            '1. PASTE ORDER IDS and check SAVED TEXT.\n'
            '2. SET SEARCH BAR, switch to TRIRIGA, click inside search once.\n'
            '3. Fill a sample ID manually. RECORD from Enter through the whole ticket.\n'
            '4. Stop with Control + Option + Escape after the search page returns.\n'
            '5. Remove the sample ID if it was completed while recording.\n'
            '6. TEST NEXT, check TRIRIGA, then RUN BATCH.\n\n'
            'Keep the same browser size and zoom. Increase a step’s wait if TRIRIGA loads slowly. '
            'The runner uses this Mac’s mouse, keyboard and clipboard. Each completed replay advances the saved queue; '
            'it cannot read whether TRIRIGA accepted the changes. If stopped mid-ticket, restore the search screen '
            'and check that ticket before restarting.')

    def close(self):
        if self.mode != 'idle':
            self.stop()
            return
        for hook in self.hooks:
            hook.stop()
        self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    if sys.platform != 'darwin':
        messagebox.showerror('ClickMate Mac', 'This launcher is for macOS. Use CLICKMATE.exe on Windows.')
        root.destroy()
        sys.exit(1)
    # A second launcher must not run another copy of the same queue simultaneously.
    import fcntl
    DATA.mkdir(parents=True, exist_ok=True)
    lock = (DATA / 'app.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        messagebox.showinfo('ClickMate is already open', 'Use the existing ClickMate window.')
        sys.exit(0)
    try:
        app = ClickMate(root)
        root.mainloop()
    except Exception as error:
        messagebox.showerror('ClickMate could not open', str(error))
        raise
