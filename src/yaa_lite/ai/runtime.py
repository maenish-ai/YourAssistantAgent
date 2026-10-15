from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import requests

from ..config import data_dir
from .profiles import AgentProfile


class LocalAIError(RuntimeError):
    """User-facing local AI failure. The technical detail is written to the AI log."""


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def log_path() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p / "local_ai.log"


def find_llama_server() -> Path:
    candidates = [
        bundle_root() / "runtime" / "llama-server.exe",
        bundle_root() / "runtime" / "llama-server",
        bundle_root() / "llama-server.exe",
        bundle_root() / "llama-server",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError("llama-server runtime is not installed in the application bundle")


def model_path(profile: AgentProfile) -> Path:
    p = bundle_root() / "models" / profile.model_filename
    if not p.exists():
        raise FileNotFoundError(f"Local model is missing: {p.name}")
    return p


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _parse_json_object(text: str) -> dict | None:
    """Normalize Hammer's textual tool-call format to the first call object.

    Hammer's native template normally emits a JSON *list* of tool calls, while
    some llama.cpp builds return one object or wrap JSON in a Markdown fence.
    Supporting all three keeps the app independent of a specific parser build.
    """
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return parsed[0]
        if isinstance(parsed, list) and not parsed:
            return None
    except Exception:
        pass
    # Last-resort compatibility for models that surround one object with prose.
    first, last = cleaned.find("{"), cleaned.rfind("}")
    if first >= 0 and last > first:
        try:
            obj = json.loads(cleaned[first:last + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


class LocalAIRuntime:
    """Lazy llama.cpp runtime tuned for 4 GB Windows laptops.

    v1.7 ships only one model (Hammer 2.1 0.5B), so the same process handles
    ordinary chat and structured tool routing. This avoids keeping two models in
    RAM and fixes the old Arabic/General model switching overhead.
    """

    def __init__(self, context_tokens: int = 2048, threads: int = 2, retry_once: bool = True, retry_count: int | None = None, performance_mode: str = "balanced"):
        self.performance_mode = performance_mode if performance_mode in {"eco","balanced","performance"} else "balanced"
        self.context_tokens = max(768, min(int(context_tokens), 2048))
        self.threads = max(1, min(int(threads), 2))
        if self.performance_mode == "eco":
            self.context_tokens = 1024; self.threads = 1
        self.retry_count = max(0, min(int(retry_count if retry_count is not None else (1 if retry_once else 0)), 2))
        self.retry_once = self.retry_count > 0  # backward-compatible attribute
        self.last_used_monotonic = 0.0
        self._proc: subprocess.Popen | None = None
        self._profile_key: str | None = None
        self._port: int | None = None
        self._safe_mode = False
        self._lock = threading.RLock()
        self._log_handle = None

    @property
    def loaded_profile(self) -> str | None:
        return self._profile_key

    def reconfigure(self, context_tokens: int, threads: int, retry_once: bool = True, retry_count: int | None = None, performance_mode: str | None = None) -> None:
        new_mode = performance_mode if performance_mode in {"eco","balanced","performance"} else self.performance_mode
        new_context = max(768, min(int(context_tokens), 2048))
        new_threads = max(1, min(int(threads), 2))
        if new_mode == "eco": new_context, new_threads = 1024, 1
        new_retries = max(0, min(int(retry_count if retry_count is not None else (1 if retry_once else 0)), 2))
        changed = (new_context, new_threads, new_retries, new_mode) != (self.context_tokens, self.threads, self.retry_count, self.performance_mode)
        self.context_tokens = new_context
        self.threads = new_threads
        self.performance_mode = new_mode
        self.retry_count = new_retries
        self.retry_once = new_retries > 0
        if changed:
            self.stop(wait=False)

    def _write_log(self, message: str) -> None:
        try:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with log_path().open("a", encoding="utf-8") as f:
                f.write(f"[{stamp}] {message}\n")
        except Exception:
            pass

    def stop(self, wait: bool = True) -> None:
        with self._lock:
            proc, self._proc = self._proc, None
            self._profile_key = None
            self._port = None
            self._safe_mode = False
            handle, self._log_handle = self._log_handle, None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
            if wait:
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        if handle:
            try:
                handle.close()
            except Exception:
                pass

    def ensure_started(
        self,
        profile: AgentProfile,
        status: Callable[[str], None] | None = None,
        safe_mode: int | bool = 0,
    ) -> None:
        with self._lock:
            if (
                self._proc
                and self._proc.poll() is None
                and self._profile_key == profile.model_filename
                and self._safe_mode == safe_mode
            ):
                self.last_used_monotonic = time.monotonic()
                return
        self.stop(wait=False)
        level = int(safe_mode)
        if status:
            if level == 0:
                status("Starting Hammer 2.1…")
            elif level == 1:
                status("Restarting Hammer in low-memory mode…")
            else:
                status("Restarting Hammer in ultra-safe mode…")

        server = find_llama_server()
        model = model_path(profile)
        port = _free_port()
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        ctx = self.context_tokens if level == 0 else (1536 if level == 1 else 1024)
        threads = self.threads if level == 0 else 1
        normal_batch = 16 if self.performance_mode == "eco" else (48 if self.performance_mode == "performance" else 32)
        batch = normal_batch if level == 0 else (16 if level == 1 else 8)
        cmd = [
            str(server),
            "--model", str(model),
            "--host", "127.0.0.1",
            "--port", str(port),
            "--ctx-size", str(ctx),
            "--threads", str(threads),
            "--batch-size", str(batch),
            "--ubatch-size", str(batch),
            "--parallel", "1",
            "--jinja",
        ]

        log_file = log_path().open("a", encoding="utf-8", errors="replace")
        self._write_log(
            f"Starting Hammer model={profile.model_filename} safe_mode={level} ctx={ctx} threads={threads} batch={batch}"
        )
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
        except Exception:
            log_file.close()
            raise

        deadline = time.monotonic() + (65 if level else 50)
        url = f"http://127.0.0.1:{port}/health"
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                log_file.close()
                self._write_log(f"llama-server exited during startup with code {proc.returncode}")
                raise RuntimeError(f"Local AI process stopped during startup (exit {proc.returncode})")
            try:
                r = requests.get(url, timeout=0.8)
                if r.status_code < 500:
                    with self._lock:
                        self._proc = proc
                        self._profile_key = profile.model_filename
                        self._port = port
                        self._safe_mode = level
                        self._log_handle = log_file
                    self.last_used_monotonic = time.monotonic()
                    if status:
                        status("Hammer 2.1 ready")
                    return
            except requests.RequestException:
                pass
            time.sleep(0.3)

        try:
            proc.terminate()
        except Exception:
            pass
        log_file.close()
        self._write_log("Hammer startup timed out")
        raise TimeoutError("Local AI did not become ready in time")

    def _post_completion(
        self,
        profile: AgentProfile,
        messages: list[dict],
        max_tokens: int,
        timeout: int,
        status: Callable[[str], None] | None,
        safe_mode: int | bool,
        tools: list[dict] | None = None,
    ) -> dict:
        self.ensure_started(profile, status=status, safe_mode=safe_mode)
        with self._lock:
            port = self._port
            proc = self._proc
        if not port or not proc or proc.poll() is not None:
            raise RuntimeError("Local AI server is unavailable")
        payload: dict = {
            "model": "local",
            "messages": [{"role": "system", "content": profile.system_prompt}] + messages,
            "temperature": 0.0 if tools else 0.35,
            "max_tokens": max(64, min(int(max_tokens), 256 if int(safe_mode) == 0 else 160)),
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if status:
            status("Hammer is choosing an action…" if tools else "Hammer is thinking…")
        r = requests.post(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        self.last_used_monotonic = time.monotonic()
        return data["choices"][0]["message"]

    def _run_with_retry(self, fn, status=None):
        attempts = 1 + self.retry_count
        last_error: Exception | None = None
        for attempt in range(attempts):
            level = attempt  # 0 normal, 1 low-memory, 2 ultra-safe
            try:
                return fn(level)
            except (requests.RequestException, OSError, RuntimeError, TimeoutError, KeyError, ValueError) as exc:
                last_error = exc
                self._write_log(f"AI attempt {attempt + 1}/{attempts} failed: {type(exc).__name__}: {exc}")
                self.stop(wait=True)
                if attempt + 1 < attempts and status:
                    if attempt == 0:
                        status("Hammer failed — retrying in low-memory mode…")
                    else:
                        status("Hammer failed again — final ultra-safe retry…")
                time.sleep(0.45)
        raise LocalAIError("Hammer could not complete the request after automatic restart attempts. Check Status for details.") from last_error

    def unload_if_idle(self, idle_minutes: int) -> bool:
        """Unload Hammer after an idle period. Returns True when a running model was stopped."""
        idle_minutes = max(0, int(idle_minutes))
        if idle_minutes == 0 or not self.loaded_profile or not self.last_used_monotonic:
            return False
        if time.monotonic() - self.last_used_monotonic < idle_minutes * 60:
            return False
        self._write_log(f"Unloading Hammer after {idle_minutes} idle minute(s)")
        self.stop(wait=False)
        return True

    def chat(
        self,
        profile: AgentProfile,
        messages: list[dict],
        max_tokens: int,
        timeout: int,
        status: Callable[[str], None] | None = None,
    ) -> str:
        def run(safe_mode: int):
            message = self._post_completion(
                profile, messages, max_tokens, timeout, status, safe_mode, tools=None
            )
            text = str(message.get("content") or "").strip()
            if not text:
                raise RuntimeError("Local AI returned an empty response")
            return _strip_reasoning(text)
        return self._run_with_retry(run, status=status)

    def tool_call(
        self,
        profile: AgentProfile,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int,
        timeout: int,
        status: Callable[[str], None] | None = None,
    ) -> dict:
        """Ask Hammer for one structured tool choice.

        llama.cpp may return OpenAI-style ``tool_calls`` or Hammer's textual
        JSON format. Both are normalized to {name, arguments, content}.
        """
        def run(safe_mode: int):
            message = self._post_completion(
                profile, messages, max_tokens, timeout, status, safe_mode, tools=tools
            )
            calls = message.get("tool_calls") or []
            if calls:
                call = calls[0] or {}
                fn = call.get("function") or {}
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                return {"name": str(fn.get("name") or ""), "arguments": args if isinstance(args, dict) else {}, "content": str(message.get("content") or "")}

            content = _strip_reasoning(str(message.get("content") or "").strip())
            obj = _parse_json_object(content)
            if obj and (obj.get("name") or obj.get("tool")):
                args = obj.get("arguments", obj.get("params", {}))
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {"value": args}
                return {"name": str(obj.get("name") or obj.get("tool")), "arguments": args if isinstance(args, dict) else {}, "content": content}
            return {"name": "respond", "arguments": {"message": content}, "content": content}

        return self._run_with_retry(run, status=status)


def _strip_reasoning(text: str) -> str:
    while "<think>" in text and "</think>" in text:
        a = text.find("<think>")
        b = text.find("</think>", a)
        if b == -1:
            break
        text = (text[:a] + text[b + len("</think>"):]).strip()
    return text.strip()
