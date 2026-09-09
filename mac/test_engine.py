import copy
import tempfile
import threading
import unittest
from pathlib import Path

from engine import Recording, Stopped, fresh_project, load_project, parse_ids, play, resolve, save_project


class FakeInput:
    def __init__(self, fail=None):
        self.events = []
        self.fail = fail

    def click(self, *point):
        self.events.append(('search_click', point))

    def wait(self, seconds, stop):
        if stop.is_set():
            raise Stopped()

    def select_all(self):
        self.events.append(('select_all',))

    def paste(self, value):
        self.events.append(('paste_id', value))

    def execute(self, action, stop):
        if self.fail == action['kind']:
            raise RuntimeError('Simulated input failure')
        self.events.append(('flow', action['kind'], action.get('key', action.get('value'))))


def sample():
    project = fresh_project()
    project.update(queue=['2245828', '2245829'], search=[120, 300],
                   values={'comment': 'Done by engineer'}, actions=[
                       dict(kind='key', key='enter', delay=0),
                       dict(kind='click', x=130, y=330, delay=2),
                       dict(kind='text', value='{{comment}}', delay=1)])
    return project


class EngineTests(unittest.TestCase):
    def test_each_id_is_pasted_before_recorded_enter_without_duplicate_navigation(self):
        project, io = sample(), FakeInput()
        saves = []
        play(project, io, threading.Event(), lambda _: None, lambda p: saves.append(p['next_index']))
        self.assertEqual(io.events, [
            ('search_click', (120, 300)), ('select_all',), ('paste_id', '2245828'),
            ('flow', 'key', 'enter'), ('flow', 'click', None), ('flow', 'text', 'Done by engineer'),
            ('search_click', (120, 300)), ('select_all',), ('paste_id', '2245829'),
            ('flow', 'key', 'enter'), ('flow', 'click', None), ('flow', 'text', 'Done by engineer')])
        self.assertEqual(saves, [1, 2])
        self.assertEqual(project['actions'][2]['value'], '{{comment}}')

    def test_failed_step_keeps_current_ticket(self):
        project = sample()
        with self.assertRaises(RuntimeError):
            play(project, FakeInput('click'), threading.Event(), lambda _: None, lambda _: None)
        self.assertEqual(project['next_index'], 0)

    def test_stop_between_tickets_never_pastes_the_next_id(self):
        project, io, stop = sample(), FakeInput(), threading.Event()
        play_persist = lambda p: stop.set()
        with self.assertRaises(Stopped):
            play(project, io, stop, lambda _: None, play_persist)
        self.assertEqual(project['next_index'], 1)
        self.assertEqual([e for e in io.events if e[0] == 'paste_id'], [('paste_id', '2245828')])

    def test_test_next_and_restart_begin_at_saved_position(self):
        project, io = sample(), FakeInput()
        play(project, io, threading.Event(), lambda _: None, lambda _: None, limit=1)
        play(project, io, threading.Event(), lambda _: None, lambda _: None, limit=1)
        self.assertEqual([e[1] for e in io.events if e[0] == 'paste_id'], ['2245828', '2245829'])

    def test_missing_saved_text_fails_before_any_click(self):
        project, io = sample(), FakeInput()
        project['values'] = {}
        with self.assertRaises(ValueError):
            play(project, io, threading.Event(), lambda _: None, lambda _: None)
        self.assertEqual(io.events, [])

    def test_recording_keeps_enter_first_text_and_delay(self):
        recording = Recording(10)
        recording.add(dict(kind='key', key='enter'), 12)
        recording.add(dict(kind='click', x=10, y=20), 16, 16.1)
        recording.text('Done ', 17)
        recording.text('by engineer', 19)
        actions = recording.finish(22, {'comment': 'Done by engineer'})
        self.assertEqual(actions[0], dict(kind='key', key='enter', delay=2))
        self.assertEqual(actions[1]['delay'], 4)
        self.assertEqual(actions[2]['value'], '{{comment}}')
        self.assertAlmostEqual(actions[2]['delay'], 0.9)
        self.assertEqual(actions[3]['delay'], 3)

    def test_cleared_flow_is_not_restored_from_seed(self):
        with tempfile.TemporaryDirectory() as folder:
            path, seed = Path(folder) / 'save.json', Path(folder) / 'seed.json'
            save_project(seed, sample())
            project = load_project(path, seed)
            project['actions'] = []
            save_project(path, project)
            self.assertEqual(load_project(path, seed)['actions'], [])
            self.assertEqual(load_project(path, seed)['queue'], ['2245828', '2245829'])

    def test_id_parsing_preserves_order(self):
        self.assertEqual(parse_ids('2245828,2245829\n2245828; 2245830'), ['2245828', '2245829', '2245830'])

    def test_save_failure_does_not_advance_in_memory(self):
        project = sample()
        def fail_save(_):
            raise OSError('Disk full')
        with self.assertRaises(OSError):
            play(project, FakeInput(), threading.Event(), lambda _: None, fail_save)
        self.assertEqual(project['next_index'], 0)


if __name__ == '__main__':
    unittest.main()
