"""
base.py

Copyright 2019 Andres Riancho

This file is part of w3af, http://w3af.org/ .

w3af is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation version 2 of the License.

w3af is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with w3af; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
"""
import os
import time
import Queue
import unittest

from w3af.core.controllers.output_manager import manager
from w3af.core.controllers.chrome.tests.helpers import set_debugging_in_output_manager
from w3af.core.controllers.chrome.crawler.main import ChromeCrawler
from w3af.core.controllers.daemons.webserver import start_webserver_any_free_port
from w3af.core.data.url.extended_urllib import ExtendedUrllib


class BaseChromeCrawlerTest(unittest.TestCase):
    SERVER_HOST = '127.0.0.1'
    SERVER_ROOT_PATH = '/tmp/'

    def __init__(self, *args, **kwargs):
        super(BaseChromeCrawlerTest, self).__init__(*args, **kwargs)
        self.server_thread = None
        self.server = None
        self.log_filename = None
        self.log = None

    def setUp(self):
        self.log_filename = set_debugging_in_output_manager()
        self.uri_opener = ExtendedUrllib()
        self.http_traffic_queue = Queue.Queue()
        self.crawler = ChromeCrawler(self.uri_opener)

    def _unittest_setup(self, request_handler_klass):
        t, s, p = start_webserver_any_free_port(self.SERVER_HOST,
                                                webroot=self.SERVER_ROOT_PATH,
                                                handler=request_handler_klass)

        self.server_thread = t
        self.server = s
        self.server_port = p

    def tearDown(self):
        while not self.http_traffic_queue.empty():
            self.http_traffic_queue.get_nowait()

        self.crawler.terminate()

        if self.server is not None:
            self.server.shutdown()
            self.server_thread.join()

        self._wait_for_output_manager_messages()

    def _wait_for_output_manager_messages(self):
        start = time.time()

        while not manager.in_queue.empty():
            time.sleep(0.1)
            spent = time.time() - start

            if spent > 2.0:
                break

    def _get_found_urls(self):
        uris = set()

        while not self.http_traffic_queue.empty():
            request, response = self.http_traffic_queue.get_nowait()
            uris.add(str(request.get_uri()))

        return uris

    def _crawl(self, url):
        self.crawler.crawl(url, self.http_traffic_queue)

        found_uris = self._get_found_urls()

        # self.crawler.print_all_console_messages()
        # self.assertEqual(self.crawler.get_js_errors(), [])
        self._parse_log()

        return found_uris

    def _format_assertion_message(self, found_uris, url, min_uris):
        all_uris_str = '\n'.join(' - %s' % i for i in found_uris)

        msg = ('The crawler found %s URIs after crawling %s and should'
               ' have found least %s. The complete list of URIs is:\n%s')
        args = (len(found_uris), url, min_uris, all_uris_str)
        return msg % args

    def assertMinURI(self, found_uris, min_uris, url):
        self.assertGreaterEqual(len(found_uris),
                                min_uris,
                                self._format_assertion_message(found_uris, url, min_uris))

    def _parse_log(self):
        self.log = LogFile(self.log_filename)

    def _log_contains(self, expected_messages):
        expected_message_list = expected_messages.split('\n')
        expected_message_list = [em.strip() for em in expected_message_list]

        i = 0
        found = []
        not_found = []

        for expected_message in expected_message_list:
            while i < len(self.log.log_messages):
                log_message = self.log.log_messages[i]
                i += 1

                if log_message.matches(expected_message):
                    found.append(expected_message)
                    break

            if expected_message not in found:
                not_found.append(expected_message)
                return found, not_found

            # reached the end of the log file without finding the message
            if i == len(self.log.log_messages):
                return found, not_found

        # all expected messages found!
        return found, not_found


class LogMessage(object):
    def __init__(self, line):
        self.line = line

    def matches(self, message):
        return message in self.line


class LogFile(object):
    def __init__(self, filename):
        self.filename = filename
        self.log_messages = []

        for line in open(self.filename):
            line = line.strip()
            self.log_messages.append(LogMessage(line))

    def matches(self, message):
        for log_message in self.log_messages:
            if log_message.matches(message):
                return True

        return False