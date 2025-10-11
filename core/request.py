"""
Class for using one generic cookie jar, emulating a single tab
"""

import requests

from core.filemanager import FileManager
from core.notification import Notification

import logging
import re
import time
import random
from urllib.parse import urljoin, urlencode

from core.reporter import ReporterObject


class WebWrapper:
    """
    WebWrapper object for sending HTTP requests
    """
    web = None
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.97 Safari/537.36',
        'upgrade-insecure-requests': '1'
    }
    endpoint = None
    logger = logging.getLogger("Requests")
    server = None
    last_response = None
    last_h = None
    priority_mode = False
    auth_endpoint = None
    reporter = None
    delay = 1.0

    def __init__(
            self,
            url,
            server=None,
            endpoint=None,
            reporter_enabled=False,
            reporter_constr=None,
            request_timeout=None,
            max_retries=3,
            retry_backoff=1.5,
    ):
        """
        Construct the session and detect variables
        """
        self.web = requests.session()
        self.auth_endpoint = url
        self.server = server
        self.endpoint = endpoint
        self.reporter = ReporterObject(enabled=reporter_enabled, connection_string=reporter_constr)
        self.request_timeout = self._normalize_timeout(request_timeout)
        self.max_retries = max(1, int(max_retries))
        self.retry_backoff = retry_backoff if retry_backoff and retry_backoff > 0 else 1.5

    def post_process(self, response):
        """
        Post-processes all requests and stores data used for the next request
        """
        xsrf = re.search('<meta content="(.+?)" name="csrf-token"', response.text)
        if xsrf:
            self.headers['x-csrf-token'] = xsrf.group(1)
            self.logger.debug("Set CSRF token")
        elif 'x-csrf-token' in self.headers:
            del self.headers['x-csrf-token']
        self.headers['Referer'] = response.url
        self.last_response = response
        get_h = re.search(r'&h=(\w+)', response.text)
        if get_h:
            self.last_h = get_h.group(1)

    def get_url(self, url, headers=None):
        """
        Fetches a URL using a basic GET request
        """
        self.headers['Origin'] = (self.endpoint if self.endpoint else self.auth_endpoint).rstrip('/')
        self._sleep_human_delay()
        url = urljoin(self.endpoint if self.endpoint else self.auth_endpoint, url)
        request_headers = headers or self.headers
        response = self._request_with_retries(
            self.web.get,
            url,
            log_action="GET",
            headers=request_headers,
        )
        if not response:
            return None

        self.post_process(response)
        if 'data-bot-protect="forced"' in response.text:
            self.logger.warning("Bot protection hit! cannot continue")
            self.reporter.report(
                0, "TWB_RECAPTCHA", "Stopping bot, press any key once captcha has been solved")
            Notification.send("Bot protection hit! cannot continue")
            input("Press any key...")
            return self.get_url(url, headers)
        return response

    def post_url(self, url, data, headers=None):
        """
        Sends a basic POST request with urlencoded postdata
        """
        self.headers['Origin'] = (self.endpoint if self.endpoint else self.auth_endpoint).rstrip('/')
        self._sleep_human_delay()
        url = urljoin(self.endpoint if self.endpoint else self.auth_endpoint, url)
        enc = urlencode(data)
        request_headers = headers or self.headers
        response = self._request_with_retries(
            self.web.post,
            url,
            log_action="POST",
            headers=request_headers,
            data=data,
            log_payload=enc,
        )
        if not response:
            return None
        self.post_process(response)
        return response

    def _sleep_human_delay(self):
        if self.priority_mode:
            return
        lower = max(0, int(3 * self.delay))
        upper = max(lower, int(7 * self.delay))
        if upper <= 0:
            return
        time.sleep(random.randint(lower, upper))

    def _retry_sleep(self, attempt_index):
        backoff_multiplier = self.retry_backoff ** max(0, attempt_index - 1)
        jitter = random.uniform(0.5, 1.5)
        base_delay = self.delay if self.delay > 0 else 1
        return max(0.5, jitter * backoff_multiplier * base_delay)

    def _normalize_timeout(self, timeout):
        if timeout is None:
            return (5, 30)
        if isinstance(timeout, (int, float)):
            value = float(timeout)
            return (value, value)
        if isinstance(timeout, (list, tuple)) and len(timeout) == 2:
            try:
                return (float(timeout[0]), float(timeout[1]))
            except (TypeError, ValueError):
                return (5, 30)
        return (5, 30)

    def _request_with_retries(self, method, url, *, log_action, log_payload=None, **kwargs):
        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = method(url=url, timeout=self.request_timeout, **kwargs)
                if log_payload:
                    self.logger.debug("%s %s %s [%d]", log_action, url, log_payload, response.status_code)
                else:
                    self.logger.debug("%s %s [%d]", log_action, url, response.status_code)
                return response
            except requests.RequestException as exc:
                last_exception = exc
                self.logger.warning(
                    "%s %s attempt %d/%d failed: %s",
                    log_action,
                    url,
                    attempt,
                    self.max_retries,
                    exc,
                )
            except Exception as exc:  # pragma: no cover - safeguard for unexpected errors
                last_exception = exc
                self.logger.warning(
                    "%s %s attempt %d/%d failed: %s",
                    log_action,
                    url,
                    attempt,
                    self.max_retries,
                    exc,
                )
            if attempt < self.max_retries:
                time.sleep(self._retry_sleep(attempt))
        if last_exception:
            self.logger.error(
                "%s %s failed after %d attempts: %s",
                log_action,
                url,
                self.max_retries,
                last_exception,
            )
        return None

    def start(self, ):
        """
        Start the bot and verify whether the last session is still valid
        """
        session_data = FileManager.load_json_file("cache/session.json")
        if session_data:
            self.web.cookies.update(session_data['cookies'])
            get_test = self.get_url("game.php?screen=overview")
            if "game.php" in get_test.url:
                return True
            self.logger.warning("Current session cache not valid")

        self.web.cookies.clear()
        cinp = input("Enter browser cookie string> ")
        cookies = {}
        cinp = cinp.strip()
        for itt in cinp.split(';'):
            itt = itt.strip()
            kvs = itt.split("=")
            k = kvs[0]
            v = '='.join(kvs[1:])
            cookies[k] = v
        self.web.cookies.update(cookies)
        self.logger.info("Game Endpoint: %s", self.endpoint)

        for c in self.web.cookies:
            cookies[c.name] = c.value

        FileManager.save_json_file({
            'endpoint': self.endpoint,
            'server': self.server,
            'cookies': cookies
        }, "cache/session.json")

    def get_action(self, village_id, action):
        """
        Runs an action on a specific village
        """
        url = "game.php?village=%s&screen=%s" % (village_id, action)
        response = self.get_url(url)
        return response

    def _parse_api_response(self, response, context):
        """Return parsed JSON data for API requests when possible."""
        if response is None:
            self.logger.warning("No response received for %s", context)
            return None
        if response.status_code != 200:
            return None
        try:
            return response.json()
        except ValueError:
            return response

    def get_api_data(self, village_id, action, params={}):

        custom = dict(self.headers)
        custom['accept'] = "application/json, text/javascript, */*; q=0.01"
        custom['x-requested-with'] = "XMLHttpRequest"
        custom['tribalwars-ajax'] = "1"
        req = {
            'ajax': action,
            'village': village_id,
            'screen': 'api'
        }
        req.update(params)
        payload = f"game.php?{urlencode(req)}"
        url = urljoin(self.endpoint, payload)
        res = self.get_url(url, headers=custom)
        return self._parse_api_response(
            res,
            f"get_api_data(action={action}, village={village_id})",
        )

    def post_api_data(self, village_id, action, params={}, data={}):
        """
        Simulates an API request
        """
        custom = dict(self.headers)
        custom['accept'] = "application/json, text/javascript, */*; q=0.01"
        custom['x-requested-with'] = "XMLHttpRequest"
        custom['tribalwars-ajax'] = "1"
        req = {
            'ajax': action,
            'village': village_id,
            'screen': 'api'
        }
        req.update(params)
        payload = f"game.php?{urlencode(req)}"
        url = urljoin(self.endpoint, payload)
        if 'h' not in data:
            data['h'] = self.last_h
        res = self.post_url(url, data=data, headers=custom)
        return self._parse_api_response(
            res,
            f"post_api_data(action={action}, village={village_id})",
        )

    def get_api_action(self, village_id, action, params={}, data={}):
        """
        Simulates an API action being triggered
        """
        custom = dict(self.headers)
        custom['Accept'] = "application/json, text/javascript, */*; q=0.01"
        custom['X-Requested-With'] = "XMLHttpRequest"
        custom['TribalWars-Ajax'] = "1"
        req = {
            'ajaxaction': action,
            'village': village_id,
            'screen': 'api'
        }
        req.update(params)
        payload = f"game.php?{urlencode(req)}"
        url = urljoin(self.endpoint, payload)
        if 'h' not in data:
            data['h'] = self.last_h
        res = self.post_url(url, data=data, headers=custom)
        return self._parse_api_response(
            res,
            f"get_api_action(action={action}, village={village_id})",
        )
