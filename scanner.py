#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import os
from aiohttp.client_exceptions import ClientConnectionError
from urllib.parse import urlparse
import async_timeout
from modules.helper import FileHelper
from modules.task_manager import TaskManager
from modules.exceptions import *
from aiohttp import ClientSession, TCPConnector
import collections
import atexit


class Scanner:
    def __init__(self, config_data):
        self.good = 0
        self.path_data = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data/')
        self.path_stats = os.path.join(self.path_data, 'config', 'stats.json')
        self.stats = FileHelper.load_config(self.path_stats)
        self.writer = FileHelper.put_line(os.path.join(self.path_data, 'good.txt'))
        self.config_data = config_data
        self.timeout = self.config_data['settings']['timeout']
        self.completed_urls = FileHelper.get_complete_urls(os.path.join(self.path_data, 'good.txt'))
        self.timeout_stats_url = collections.defaultdict(int)
        self.tcp_connector = None
        self.client_session = None
        self.stop_loop = False
        self.need_refresh_connect = False
        self.task_manager = TaskManager(asyncio.get_event_loop())
        self.sem = asyncio.BoundedSemaphore(self.config_data['settings']['threads'])
        self.lock = asyncio.Lock()

    def get_source_line(self):
        url_in_loop = False
        gen_paths = FileHelper.get_line(os.path.join(self.path_data, 'paths.txt'), int(self.stats['paths']))
        for path, path_iter in gen_paths:
            self.stats['urls'] = 0 if url_in_loop else self.stats['urls']
            gen_urls = FileHelper.get_line(os.path.join(self.path_data, 'urls.txt'), int(self.stats['urls']))
            for url, url_iter in gen_urls:
                url_in_loop = True
                if urlparse(url).hostname in self.completed_urls:
                    continue
                self.stats['paths'], self.stats['urls'] = path_iter, url_iter

                yield (url, path)

    def refresh_stats(self):
        self.stats['total'] += 1
        if self.stats['total'] % self.config_data['settings']['save_every_time'] == 0:
            FileHelper.save_stats(self.path_stats, self.stats)
        if self.stats['total'] % self.config_data['settings']['refresh_connector_every_time'] == 0:
            self.need_refresh_connect = True

    def add_good(self, url, url_host):
        self.good += 1
        if self.config_data['settings']['break_on_good']:
            self.add_to_completed_urls(url_host)
        self.task_manager.complete_task(url_host)
        self.writer.send(url)
        print("{} - Good: {}".format(url, self.good))

    def add_to_completed_urls(self, url_host):
        if url_host not in self.completed_urls:
            self.completed_urls.append(url_host)

    def _result_callback(self, url_host, future):
        # Record processed we can now release the lock
        self.sem.release()
        if future.cancelled():
            print("{} - Cancelled".format(url_host))
        # Handle known exceptions, barf on other ones
        elif future.exception() is not None:
            print("{} - Error: {}".format(url_host, str(type(future.exception()))))
            if isinstance(future.exception(), asyncio.TimeoutError):
                self.timeout_stats_url[url_host] += 1
            if isinstance(future.exception(), ClientConnectionError) or \
                    self.timeout_stats_url[url_host] >= self.config_data['settings']['max_timeouts']:
                self.add_to_completed_urls(url_host)
                self.task_manager.complete_task(url_host)
                print("{} - Removed From Queue".format(url_host, str(type(future.exception()))))
        # Output result
        else:
            response_text, response_url = future.result()
            if self.config_data['parse']['contentFind'] in response_text:
                self.add_good(response_url, url_host)

        self.refresh_stats()
        self.task_manager.remove_task(url_host, future)

    async def refresh_connector(self):
        print("-------------[ Refresh TCP Connector ]-------------")
        self.tcp_connector.close()
        self.client_session.close()
        print("-------------[ Wait until the connector is refreshed... ]-------------")
        await asyncio.sleep(self.config_data['settings']['time_waiting_while_refresh'])
        self.tcp_connector = TCPConnector(verify_ssl=False,
                                          force_close=True,
                                          enable_cleanup_closed=True,
                                          limit=None)
        self.client_session = ClientSession(connector=self.tcp_connector,
                                            headers={"User-Agent": self.config_data['settings']['user_agent']})
        self.need_refresh_connect = False

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
        return await self.fetch(url, session)

    async def run(self):
        atexit.register(self.exit_handler)
        self.writer.send(None)
        FileHelper.save_stats(self.path_stats, self.stats)
        # Create client session that will ensure we don't open new connection
        # per each request.
        self.tcp_connector = TCPConnector(verify_ssl=False,
                                          force_close=True,
                                          enable_cleanup_closed=True,
                                          limit=None)
        self.client_session = ClientSession(connector=self.tcp_connector,
                                            headers={"User-Agent": self.config_data['settings']['user_agent']})
        for url, path in self.get_source_line():
            await self.sem.acquire()
            async with self.lock:
                if self.need_refresh_connect:
                    while False in list(map(lambda future: future.done(), self.task_manager.tasks['all_tasks'])):
                        await asyncio.sleep(1)
                    await self.refresh_connector()

            self.task_manager.run_task(url, path, self.client_session,
                                       self.bound_fetch,
                                       self._result_callback)
            if self.stop_loop:
                break
        await asyncio.gather(*self.task_manager.tasks['all_tasks'], return_exceptions=True)
        if not self.stop_loop:
            self.stats = {'urls': 0, 'paths': 0, 'total': 0}
            FileHelper.save_stats(self.path_stats, self.stats)
            self.writer.send('Close')
        await self.client_session.close()
        self.task_manager.loop.stop()

    def exit_handler(self):
        if len(self.task_manager.tasks['all_tasks']) == 0:
            self.task_manager.loop.close()
            print("-------------[ Done ]-------------")
            return

        print("-------------[ Wait until the tasks is completed... ]-------------")
        self.stop_loop = True
        try:
            self.task_manager.loop.run_forever()
        finally:
            FileHelper.save_stats(self.path_stats, self.stats)
            self.writer.send('Close')
        self.task_manager.loop.close()
        print("-------------[ Done ]-------------")


def main():
    config_data = FileHelper.load_config(
        os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data/config/config.json'))
    scanner = Scanner(config_data)
    loop = asyncio.get_event_loop()
    asyncio.ensure_future(scanner.run(), loop=loop)
    loop.run_forever()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt as exc:
        pass
