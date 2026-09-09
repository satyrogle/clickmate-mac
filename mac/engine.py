"""ClickMate Mac data/recording/playback logic. No OS hooks during import."""
from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from pathlib import Path


def parse_ids(text):
    return list(dict.fromkeys(re.findall(r'\b\d{5,12}\b', text)))


def fresh_project():
    return dict(version=1, queue=[], next_index=0, actions=[], search=None,
                values={}, displays=[], search_displays=[], extra_wait=1.0, reload_wait=12.0)


def load_project(path, seed):
    source = path if path.exists() else seed
    if not source.exists():
        return fresh_project()
    data = json.loads(source.read_text(encoding='utf-8-sig'))
    project = fresh_project()
    project.update(data)
    if not isinstance(project['queue'], list) or not isinstance(project['actions'], list):
        raise ValueError('Saved queue or flow is invalid. Restore your backup JSON.')
    if not 0 <= project['next_index'] <= len(project['queue']):
        raise ValueError('Saved queue position is invalid.')
    return project


def save_project(path, project):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.save-', delete=False) as handle:
            name = handle.name
            json.dump(project, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


TOKEN = re.compile(r'\{\{([A-Za-z][A-Za-z0-9_]*)\}\}')


def resolve(text, values):
    def replace(match):
        if match[1] not in values:
            raise ValueError('Saved text is missing: ' + match[1])
        return str(values[match[1]])
    return TOKEN.sub(replace, text)


class Recording:
    def __init__(self, started):
        self.last = started
        self.actions = []
        self.buffer = ''
        self.text_started = started
        self.text_ended = started

    def text(self, text, at):
        if not self.buffer:
            self.text_started = at
        self.buffer += text
        self.text_ended = at

    def flush(self):
        if self.buffer:
            self.actions.append(dict(kind='text', value=self.buffer,
                                     delay=max(0, self.text_started - self.last)))
            self.last = self.text_ended
            self.buffer = ''

    def add(self, action, at, ended=None):
        self.flush()
        self.actions.append(dict(action, delay=max(0, at - self.last)))
        self.last = at if ended is None else ended

    def finish(self, at, values):
        self.flush()
        # Preserve the recorded return-to-search wait as part of the flow.
        self.actions.append(dict(kind='wait', delay=max(0, at - self.last)))
        for action in self.actions:
            if action['kind'] == 'text':
                for name, value in sorted(values.items(), key=lambda x: len(x[1]), reverse=True):
                    if value and action['value'] == value:
                        action['value'] = '{{' + name + '}}'
                        break
        return self.actions


class Stopped(Exception):
    pass


def play(project, io, stop, notify, persist, limit=None):
    """Paste each queued ID, then run the recorded Enter and nested-link steps.

    io.wait must be interruptible; io.execute is the platform boundary.
    Queue advancement means all recorded actions ran, not server-side completion.
    """
    actions = copy.deepcopy(project['actions'])
    if not actions or actions[0].get('kind') != 'key' or actions[0].get('key') != 'enter':
        raise ValueError('The flow must start with Enter. Record from the filled search bar.')
    if not project['search']:
        raise ValueError('Set the search bar first.')
    for action in actions:
        if action['kind'] == 'text':
            action['value'] = resolve(action['value'], project['values'])
    start = project['next_index']
    end = len(project['queue']) if limit is None else min(len(project['queue']), start + limit)
    if start == end:
        raise ValueError('The queue is finished. Paste a new list to start again.')

    def check():
        if stop.is_set():
            raise Stopped('Stopped. The unfinished ticket stays at the front of the queue.')

    for index in range(start, end):
        check()
        order_id = project['queue'][index]
        notify(f'Work order {order_id}: pasting into search bar')
        io.click(*project['search'])
        io.wait(0.3, stop)
        check()
        io.select_all()
        io.wait(0.15, stop)
        check()
        io.paste(order_id)
        io.wait(0.5, stop)
        for number, action in enumerate(actions, 1):
            notify(f'{order_id} | step {number}/{len(actions)} | {action["kind"]}')
            extra = project['extra_wait'] if action['kind'] in ('click', 'drag') else 0
            # Do not stretch a recorded double-click into two single clicks.
            if (number > 1 and action['kind'] == 'click'
                    and actions[number - 2]['kind'] == 'click'
                    and action['delay'] < 0.5
                    and action.get('x') == actions[number - 2].get('x')
                    and action.get('y') == actions[number - 2].get('y')):
                extra = 0
            io.wait(action['delay'] + extra, stop)
            check()
            io.execute(action, stop)
        check()
        project['next_index'] = index + 1
        try:
            persist(project)
        except Exception:
            project['next_index'] = index
            raise
        notify(f'Flow finished for {order_id}. {len(project["queue"]) - index - 1} IDs remain.')
        if index + 1 < end:
            io.wait(project['reload_wait'], stop)
