"""macOS-only input adapter. Uses logical display coordinates, no screenshots."""
import subprocess

from engine import Stopped


def clipboard_text():
    return subprocess.run(['/usr/bin/pbpaste'], capture_output=True, check=True,
                          timeout=3).stdout.decode('utf-8')


def permissions_ready():
    import HIServices
    import Quartz
    access = bool(HIServices.AXIsProcessTrusted())
    listen = bool(Quartz.CGPreflightListenEventAccess()) if hasattr(Quartz, 'CGPreflightListenEventAccess') else access
    return access and listen


def display_layout():
    import Quartz
    error, displays, count = Quartz.CGGetActiveDisplayList(16, None, None)
    if error:
        raise RuntimeError('Could not read Mac display coordinates.')
    result = []
    for display in displays[:count]:
        bounds = Quartz.CGDisplayBounds(display)
        result.append([int(bounds.origin.x), int(bounds.origin.y),
                       int(bounds.size.width), int(bounds.size.height)])
    return sorted(result)


class MacInput:
    def __init__(self):
        from pynput import keyboard, mouse
        self.keyboard = keyboard
        self.mouse = mouse
        self.keys = keyboard.Controller()
        self.pointer = mouse.Controller()

    @staticmethod
    def wait(seconds, stop):
        if stop.wait(max(0, seconds)):
            raise Stopped('Stopped. The unfinished ticket remains in the queue.')

    def click(self, x, y, button='left'):
        if not any(l <= x < l + w and t <= y < t + h for l, t, w, h in display_layout()):
            raise ValueError('A recorded click is outside the current displays. Re-record on this Mac.')
        self.pointer.position = (x, y)
        self.pointer.click(getattr(self.mouse.Button, button))

    def key(self, name):
        return getattr(self.keyboard.Key, name) if hasattr(self.keyboard.Key, name) else name

    def combo(self, names):
        pressed = []
        try:
            for name in names:
                key = self.key(name)
                self.keys.press(key)
                pressed.append(key)
        finally:
            for key in reversed(pressed):
                self.keys.release(key)

    def select_all(self):
        self.combo(['cmd', 'a'])

    def paste(self, text):
        # No clipboard sharing with the Windows computer; this is the Mac clipboard.
        subprocess.run(['/usr/bin/pbcopy'], input=text.encode('utf-8'), check=True, timeout=3)
        self.combo(['cmd', 'v'])

    def execute(self, action, stop):
        kind = action['kind']
        if kind == 'click':
            self.click(action['x'], action['y'], action.get('button', 'left'))
        elif kind == 'drag':
            self.pointer.position = (action['x'], action['y'])
            button = getattr(self.mouse.Button, action.get('button', 'left'))
            self.pointer.press(button)
            try:
                for i in range(1, 21):
                    self.wait(action.get('duration', 0.4) / 20, stop)
                    self.pointer.position = (action['x'] + (action['end_x'] - action['x']) * i / 20,
                                             action['y'] + (action['end_y'] - action['y']) * i / 20)
            finally:
                self.pointer.release(button)
        elif kind == 'scroll':
            self.pointer.position = (action['x'], action['y'])
            self.pointer.scroll(action['dx'], action['dy'])
        elif kind == 'key':
            self.combo([action['key']])
        elif kind == 'combo':
            self.combo(action['keys'])
        elif kind == 'text':
            self.paste(action['value'])
        elif kind != 'wait':
            raise ValueError('Unsupported recorded action: ' + kind)
