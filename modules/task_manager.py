#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import collections
import asyncio
import functools
from urllib.parse import urlparse
import concurrent.futures


class TaskManager:
    def __init__(self, loop):
        self.loop = loop
        self.tasks = collections.defaultdict(list)

    def complete_task(self, url_host):
        map(lambda _future: _future.cancel(), self.tasks[url_host])

    def run_task(self, url, path, session, future_call, cb_future):
        task = asyncio.ensure_future(
            future_call(url.rstrip('/') + '/' + path.lstrip('/'), session))
        url_host = urlparse(url).hostname
        task.add_done_callback(functools.partial(cb_future, url_host))
        self.add_task(url_host, task)

    def add_task(self, url_host, future):
        self.tasks[url_host].append(future)
        self.tasks['all_tasks'].append(future)

    def remove_task(self, url_host, future):
        self.tasks[url_host].remove(future)
        self.tasks['all_tasks'].remove(future)
