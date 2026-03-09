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

    def __init__(self, url, server=None, endpoint=None, reporter_enabled=False, reporter_constr=None):
        """
        Construct the session and detect variables
        """
        self.web = requests.session()
        self.auth_endpoint = url
        self.server = server
        self.endpoint = endpoint
        self.reporter = ReporterObject(enabled=reporter_enabled, connection_string=reporter_constr)
        self.logger = logging.getLogger("Requests")
        # Per-instance mutable headers dict — must NOT be a class-level default
        self.headers: dict = {
            'user-agent': 'Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.97 Safari/537.36',
            'upgrade-insecure-requests': '1',
        }
        self.last_response = None
        self.last_h = None
        self.priority_mode = False
        self.delay = 1.0

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
        if not self.priority_mode:
            time.sleep(random.randint(int(3 * self.delay), int(7 * self.delay)))
        url = urljoin(self.endpoint if self.endpoint else self.auth_endpoint, url)
        if not headers:
            headers = self.headers
        try:
            res = self.web.get(url=url, headers=headers)
            self.logger.debug("GET %s [%d]", url, res.status_code)
            self.post_process(res)
            if 'data-bot-protect="forced"' in res.text:
                self.logger.warning("Bot protection hit! cannot continue")
                self.reporter.report(
                    0, "TWB_RECAPTCHA", "Stopping bot, press any key once captcha has been solved")
                Notification.send("Bot protection hit! cannot continue")
                input("Press any key...")
                return self.get_url(url, headers)
            return res
        except Exception as e:
            self.logger.warning("GET %s: %s", url, str(e))
            return None

    def post_url(self, url, data, headers=None):
        """
        Sends a basic POST request with urlencoded postdata
        """
        if not self.priority_mode:
            time.sleep(
                random.randint(int(3 * self.delay), int(7 * self.delay))
            )
        self.headers['Origin'] = (self.endpoint if self.endpoint else self.auth_endpoint).rstrip('/')
        url = urljoin(self.endpoint if self.endpoint else self.auth_endpoint, url)
        enc = urlencode(data)
        if not headers:
            headers = self.headers
        try:
            res = self.web.post(url=url, data=data, headers=headers)
            self.logger.debug("POST %s %s [%d]", url, enc, res.status_code)
            self.post_process(res)
            return res
        except Exception as e:
            self.logger.warning("POST %s %s: %s", url, enc, str(e))
            return None

    def set_cookies(self, cookies: dict):
        """
        Manually inject cookies into headers bypassing requests jar mutating pl_auth
        """
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
        for k, v in cookies.items():
            if k == "Cookie":
                cookie_str = v
                break
        self.headers['Cookie'] = cookie_str
        self.web.cookies.clear()
        
    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    _FORBIDDEN_SERVERS = ["www", "plemiona", "tribalwars", "die-staemme"]

    def _apply_endpoint_from_session(self, session_data: dict) -> None:
        """Update self.endpoint and self.server from a session dict if the
        extracted server name is not on the forbidden list."""
        ep = session_data.get("endpoint", "")
        if not ep:
            return
        try:
            extracted = ep.split("//")[1].split(".")[0]
            if extracted and extracted not in self._FORBIDDEN_SERVERS:
                self.endpoint = ep
                self.server = extracted
        except Exception:
            pass

    def _cookies_to_header_string(self, cookies: dict) -> str:
        """Convert a cookies dict to a raw Cookie header string.

        If the dict has a single 'Cookie' key with the raw string already
        encoded, return that directly (legacy browser-extension format).
        """
        if "Cookie" in cookies:
            return cookies["Cookie"]
        return "; ".join(f"{k}={v}" for k, v in cookies.items())

    def _verify_session_via_urllib(self, cookie_str: str) -> bool:
        """Verify that the supplied cookie string produces a valid session.

        Uses urllib (not requests) so the Cookie header is sent verbatim
        without the requests library re-encoding auth tokens.
        Returns True on HTTP 200, False otherwise.
        """
        import urllib.request

        class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def http_error_302(self, req, fp, code, msg, headers):  # noqa: N802
                return fp

        test_url = urljoin(self.endpoint, "game.php?screen=overview")
        opener = urllib.request.build_opener(_NoRedirectHandler())
        req = urllib.request.Request(test_url)
        req.add_header("User-Agent", self.headers.get("user-agent", ""))
        req.add_header("Cookie", cookie_str)
        try:
            res = opener.open(req)
            return res.getcode() == 200
        except Exception as e:
            self.logger.warning("Session verification request failed: %s", e)
            return False

    def _load_session_file(self) -> dict | None:
        """Load and return the session cache file, or None on any error."""
        try:
            return FileManager.load_json_file("cache/session.json")
        except Exception:
            return None

    def _remove_session_file(self) -> None:
        """Delete the session cache file, ignoring errors."""
        try:
            import os as _os
            _os.remove("cache/session.json")
        except Exception:
            pass

    def _try_apply_cached_session(self, session_data: dict) -> bool:
        """Apply a session dict (cookies + endpoint), verify it, return True on success."""
        self._apply_endpoint_from_session(session_data)

        # Sync user-agent from browser into config
        if session_data.get("user_agent"):
            self.headers["user-agent"] = session_data["user_agent"]
            try:
                conf = FileManager.load_json_file("config.json")
                if conf:
                    conf["bot"]["user_agent"] = session_data["user_agent"]
                    FileManager.save_json_file(conf, "config.json")
            except Exception:
                pass

        cookie_str = self._cookies_to_header_string(session_data["cookies"])
        self.headers["Cookie"] = cookie_str
        self.web.cookies.clear()

        self.logger.info("Loaded %d cookies from session cache", len(session_data["cookies"]))
        self.logger.debug("Verifying session against: %s", self.endpoint)

        if self._verify_session_via_urllib(cookie_str):
            self.logger.info("Session verified successfully.")
            return True

        self.logger.warning(
            "Session cache invalid (server rejected cookies). Removing cache."
        )
        self._remove_session_file()
        return False

    def _wait_for_cookie_input(self) -> str:
        """Block until the user pastes a cookie string into stdin.

        Polls stdin with a 1-second select timeout so that the session file
        written by the web panel is also checked on every iteration.
        Returns the raw cookie string entered by the user, or "" if the
        session file was populated before any keyboard input arrived (caller
        should check the file again).
        """
        import sys
        import select

        while True:
            session_data = self._load_session_file()
            if session_data and session_data.get("cookies"):
                # Web panel wrote the session — signal caller via empty string
                return ""

            if sys.stdin in select.select([sys.stdin], [], [], 1.0)[0]:
                line = sys.stdin.readline().strip()
                if line:
                    return line

    def start(self):
        """Start the bot and verify whether the last session is still valid."""
        # 1. Try existing session cache
        session_data = self._load_session_file()
        if session_data:
            self._apply_endpoint_from_session(session_data)
            self.set_cookies(session_data["cookies"])
            test = self.get_url("game.php?screen=overview")
            if test and "game.php" in test.url:
                return True
            self.logger.warning("Existing session cache not valid, clearing.")
            self._remove_session_file()

        # 2. Wait for session — either from web panel file or keyboard input
        self.web.cookies.clear()
        print(
            "Waiting for browser cookie... "
            "(Use the Chrome Extension to sync automatically or paste the string here and press Enter)"
        )

        while True:
            session_data = self._load_session_file()
            if session_data and session_data.get("cookies"):
                if self._try_apply_cached_session(session_data):
                    return True
                # Session file was invalid and removed; keep waiting
                continue

            raw_input = self._wait_for_cookie_input()
            if not raw_input:
                # Session file appeared while waiting — loop back to check it
                continue

            # User pasted a cookie string manually
            break

        # 3. Parse manually-entered cookie string
        cookies: dict = {}
        for part in raw_input.split(";"):
            part = part.strip()
            if "=" in part:
                k, _, v = part.partition("=")
                cookies[k.strip()] = v.strip()

        self.web.cookies.update(cookies)
        self.logger.info("Game Endpoint: %s", self.endpoint)

        # Merge cookies from the requests jar back into the dict
        for c in self.web.cookies:
            cookies[c.name] = c.value

        FileManager.save_json_file(
            {"endpoint": self.endpoint, "server": self.server, "cookies": cookies},
            "cache/session.json",
        )
        return True

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
