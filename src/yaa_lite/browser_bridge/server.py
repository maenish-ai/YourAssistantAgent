from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable


class BrowserBridge:
    """Local command bridge for the optional normal-browser extension.

    The bridge never exposes a public network socket: it binds only to
    127.0.0.1. Commands are allow-listed by the extension and results are
    returned by an opaque command id.
    """

    def __init__(self, port: int = 8765, activity: Callable[[str, str], None] | None = None):
        self.port = port
        self.activity = activity or (lambda *_: None)
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.last_seen = 0.0
        self.browser = ""
        self.tabs = 0
        self._lock = threading.RLock()
        self._commands: list[dict] = []
        self._results: dict[str, dict] = {}
        self._result_events: dict[str, threading.Event] = {}

    @property
    def connected(self) -> bool:
        return bool(self.last_seen and time.time() - self.last_seen < 10)

    def status_text(self) -> str:
        if not self.connected:
            return "not_connected"
        return f"connected — {self.browser or 'browser'} — {self.tabs} tab(s)"

    def queue_command(self, action: str, **arguments) -> str:
        if action not in {"open_url", "active_page", "extract_links", "click_text", "click_selector", "type_selector", "probe_url", "discover_facebook_groups", "facebook_session"}:
            raise ValueError(f"Browser action not allowed: {action}")
        if action == "discover_facebook_groups":
            arguments["limit"] = max(1, min(int(arguments.get("limit", 500)), 1000))
            arguments["deep"] = bool(arguments.get("deep", False))
        cid = uuid.uuid4().hex
        cmd = {"id": cid, "action": action, "arguments": arguments, "created_at": time.time()}
        with self._lock:
            self._commands.append(cmd)
            self._result_events[cid] = threading.Event()
        self.activity("browser_command_queued", f"{action}; id={cid[:8]}")
        return cid

    def execute(self, action: str, timeout: float = 15.0, **arguments) -> dict:
        if not self.connected:
            raise RuntimeError("Normal browser extension is not connected")
        # Install the deadline while holding the same lock used by the HTTP
        # poller, so a queued command cannot escape before its expiry is set.
        with self._lock:
            cid = self.queue_command(action, **arguments)
            event = self._result_events[cid]
            duration = max(1.0, float(timeout))
            for command in self._commands:
                if command["id"] == cid:
                    command["expires_at"] = time.time() + duration
                    break
        try:
            if not event.wait(timeout=duration):
                raise TimeoutError(f"Browser command timed out: {action}")
            with self._lock:
                return self._results.pop(cid, {"ok": False, "error": "missing result"})
        finally:
            # A timed-out click/type/open must never run on a later poll. Results
            # arriving after timeout are ignored by the HTTP handler too.
            with self._lock:
                self._commands = [c for c in self._commands if c["id"] != cid]
                self._results.pop(cid, None)
                self._result_events.pop(cid, None)

    def start(self) -> bool:
        if self.thread and self.thread.is_alive():
            return True
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code: int, payload: dict):
                raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _json_body(self):
                try:
                    size = int(self.headers.get("content-length") or 0)
                    return json.loads(self.rfile.read(size) or b"{}")
                except Exception:
                    return {}

            def do_OPTIONS(self):  # noqa: N802
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "content-type")
                self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
                self.end_headers()

            def do_GET(self):  # noqa: N802
                if self.path.startswith("/ping"):
                    return self._send(200, {"ok": True, "app": "Your Assistant Agent", "connected": bridge.connected})
                if self.path.startswith("/next-command"):
                    with bridge._lock:
                        # Drop commands that have become too old before the extension sees them.
                        now = time.time()
                        bridge._commands = [c for c in bridge._commands
                                            if now < c.get("expires_at", c.get("created_at", now) + 60)]
                        cmd = bridge._commands.pop(0) if bridge._commands else None
                    return self._send(200, {"ok": True, "command": cmd})
                return self._send(404, {"ok": False})

            def do_POST(self):  # noqa: N802
                body = self._json_body()
                if self.path.startswith("/hello"):
                    was_connected = bridge.connected
                    with bridge._lock:
                        bridge.last_seen = time.time()
                        bridge.browser = str(body.get("browser") or "")[:80]
                        bridge.tabs = int(body.get("tabs") or 0)
                    if not was_connected:
                        bridge.activity("browser_extension_connected", bridge.status_text())
                    return self._send(200, {"ok": True})
                if self.path.startswith("/command-result"):
                    cid = str(body.get("id") or "")
                    if not cid:
                        return self._send(400, {"ok": False})
                    result = body.get("result") if isinstance(body.get("result"), dict) else {"ok": False, "error": "invalid result"}
                    with bridge._lock:
                        event = bridge._result_events.get(cid)
                        if event is None:
                            return self._send(200, {"ok": True, "ignored": True})
                        bridge._results[cid] = result
                        event.set()
                    bridge.activity("browser_command_result", f"id={cid[:8]}; ok={bool(result.get('ok'))}")
                    return self._send(200, {"ok": True})
                return self._send(404, {"ok": False})

            def log_message(self, fmt, *args):
                return

        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
            self.port = self.server.server_address[1]
        except OSError:
            self.activity("browser_bridge_error", f"port={self.port}; unavailable")
            return False
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name="yaa-browser-bridge")
        self.thread.start()
        self.activity("browser_bridge_started", f"127.0.0.1:{self.port}")
        return True

    def stop(self) -> None:
        if self.server:
            try:
                self.server.shutdown(); self.server.server_close()
            except Exception:
                pass
        self.server = None; self.thread = None
