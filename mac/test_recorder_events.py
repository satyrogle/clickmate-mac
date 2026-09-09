import queue
import threading
import unittest
from unittest.mock import patch

from clickmate import ClickMate
from engine import Recording


class RecorderEventsTests(unittest.TestCase):
    def setUp(self):
        self.app = ClickMate.__new__(ClickMate)
        self.app.mode = 'recording'
        self.app.recording = Recording(0)
        self.app.mouse_down = {}
        self.app.modifiers = set()
        self.app.events = queue.Queue()
        self.app.stop_event = threading.Event()

    def enter(self):
        self.app.consume(('key', 1, 'enter', None, []))

    def test_focus_click_and_typed_id_are_ignored_before_enter(self):
        self.app.consume(('mouse', .1, 10, 20, 'left', True))
        self.app.consume(('mouse', .2, 10, 20, 'left', False))
        self.app.consume(('key', .3, "'1'", '1', []))
        self.enter()
        self.app.consume(('mouse', 2, 50, 60, 'left', True))
        self.app.consume(('mouse', 2.1, 50, 60, 'left', False))
        self.assertEqual([a['kind'] for a in self.app.recording.actions], ['key', 'click'])
        self.assertEqual(self.app.recording.actions[0]['key'], 'enter')
        self.assertEqual(self.app.recording.actions[1]['x'], 50)

    def test_command_v_remembers_literal_text(self):
        self.enter()
        with patch('mac_input.clipboard_text', return_value='Engineer’s note £10'):
            self.app.consume(('key', 2, "'v'", 'v', ['cmd']))
        self.assertEqual(self.app.recording.actions[1]['value'], 'Engineer’s note £10')

    def test_stop_is_immediate_even_before_ui_queue_is_processed(self):
        class Key:
            def __str__(self):
                return 'Key.esc'
        self.app.modifiers = {'ctrl', 'alt'}
        self.app.key_press(Key())
        self.assertTrue(self.app.stop_event.is_set())
        self.assertEqual(self.app.events.get_nowait()[0], 'stop')


if __name__ == '__main__':
    unittest.main()
