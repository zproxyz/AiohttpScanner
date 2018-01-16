#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import os
import argparse
import json
import functools
import async_timeout
import concurrent.futures
from aiohttp import ClientSession, TCPConnector


class StatusError(Exception):
    """Base class for exceptions in this module."""
    pass


class Scanner:
    def __init__(self, config_data):
        self.good = 0
        self.path_data = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data/')
        self.path_stats = os.path.join(self.path_data, 'stats.json')
        self.stats = load_config(self.path_stats)
        self.reader = get_line(os.path.join(self.path_data, 'urls.txt'), int(self.stats['urls']))
        self.writer = put_line(os.path.join(self.path_data, 'good.txt'))
        self.config_data = config_data
        self.timeout = self.config_data['settings']['timeout']
        self.tasks = []
        # create instance of Semaphore
        self.sem = asyncio.BoundedSemaphore(self.config_data['settings']['threads'])

    def _result_callback(self, url, future):
        # Record processed we can now release the lock
        self.sem.release()
        if future.cancelled():
            print("{} - Cancelled".format(url))
        # Handle known exceptions, barf on other ones
        elif future.exception() is not None:
            print("{} - Error: {}".format(url, str(type(future.exception()))))
        # Output result
        else:
            response_text, response_url = future.result()
            if self.config_data['parse']['contentFind'] in response_text:
                self.good += 1
                self.writer.send(response_url)
                print("{} - Good: {}".format(response_url, self.good))
        self.stats['urls'] += 1
        if self.stats['urls'] % 1000 == 0:
            save_stats(self.path_stats, self.stats)
        self.tasks.remove(future)

    async def fetch(self, url, session):
        try:
            async with async_timeout.timeout(self.timeout):
                async with session.get(url, max_redirects=10) as response:
                    if response.status != 200:
                        raise StatusError
                    return await response.text(), str(response.url)
        except Exception as ex:
            raise ex

    async def bound_fetch(self, url, session):
        res = await self.fetch(url, session)
        return res

    async def run(self):
        self.writer.send(None)
        save_stats(self.path_stats, self.stats)
        # Create client session that will ensure we dont open new connection
        # per each request.
        tcp_connector = TCPConnector(verify_ssl=False,
                                     force_close=True,
                                     enable_cleanup_closed=True,
                                     limit=None)
        async with ClientSession(connector=tcp_connector,
                                 headers={
                                     "User-Agent": 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:55.0) '
                                                   'Gecko/20100101 Firefox/55.0'}) as session:
            for url in self.reader:
                await self.sem.acquire()
                task = asyncio.ensure_future(
                    self.bound_fetch(url.strip() + self.config_data['parse']['urlAdd'], session))
                task.add_done_callback(functools.partial(self._result_callback, url.strip()))
                self.tasks.append(task)
            await asyncio.gather(*self.tasks, return_exceptions=True)
            self.stats['urls'] = 0
            save_stats(self.path_stats, self.stats)
            self.writer.send('Close')


def get_line(path_file, offset=0):
    with open(path_file) as file:
        for i, line in enumerate(file):
            if offset != 0 and i < offset:
                continue
            yield line


def put_line(path_file):
    with open(path_file, 'w') as file:
        while True:
            line = yield
            if line is 'Close':
                break
            file.write(line + '\n')
            file.flush()
            os.fsync(file.fileno())
    yield ([])


def load_config(path_file):
    with open(path_file) as json_data_file:
        data = json.load(json_data_file)
    return data


def save_stats(path_file, data):
    with open(path_file, 'w') as outfile:
        json.dump(data, outfile)


def main():
    config_data = load_config(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data/config.json'))
    scanner = Scanner(config_data)
    loop = asyncio.get_event_loop()
    future = asyncio.ensure_future(scanner.run())
    loop.run_until_complete(future)


if __name__ == '__main__':
    main()
