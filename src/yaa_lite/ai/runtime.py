from __future__ import annotations

import os
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


class LocalAIRuntime:
    """Lazy one-model-at-a-time llama.cpp runtime tuned for 4 GB Windows laptops."""

    def __init__(self, context_tokens: int = 768, threads: int = 2, retry_once: bool = True):
        self.context_tokens = max(512, min(int(context_tokens), 1024))
        self.threads = max(1, min(int(threads), 2))
        self.retry_once = bool(retry_once)
        self._proc: subprocess.Popen | None = None
        self._profile_key: str | None = None
        self._port: int | None = None
        self._safe_mode = False
        self._lock = threading.RLock()
        self._log_handle = None

    @property
    def loaded_profile(self) -> str | None:
        return self._profile_key

    def reconfigure(self, context_tokens: int, threads: int, retry_once: bool = True) -> None:
        new_context = max(512, min(int(context_tokens), 1024))
        new_threads = max(1, min(int(threads), 2))
        changed = (new_context, new_threads, bool(retry_once)) != (
            self.context_tokens,
            self.threads,
            self.retry_once,
        )
        self.context_tokens = new_context
        self.threads = new_threads
        self.retry_once = bool(retry_once)
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
        safe_mode: bool = False,
    ) -> None:
        with self._lock:
            if (
                self._proc
                and self._proc.poll() is None
                and self._profile_key == profile.key
                and self._safe_mode == safe_mode
            ):
                return
        self.stop(wait=False)
        if status:
            status("Starting local AI…" if not safe_mode else "Restarting AI in low-memory mode…")

        server = find_llama_server()
        model = model_path(profile)
        port = _free_port()
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        ctx = 512 if safe_mode else self.context_tokens
        threads = 1 if safe_mode else self.threads
        batch = 16 if safe_mode else 32
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
        ]

        log_file = log_path().open("a", encoding="utf-8", errors="replace")
        self._write_log(
            f"Starting profile={profile.key} safe_mode={safe_mode} ctx={ctx} threads={threads} batch={batch}"
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

        deadline = time.monotonic() + (55 if safe_mode else 45)
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
                        self._profile_key = profile.key
                        self._port = port
                        self._safe_mode = safe_mode
                        self._log_handle = log_file
                    if status:
                        status("Local AI ready")
                    return
            except requests.RequestException:
                pass
            time.sleep(0.3)

        try:
            proc.terminate()
        except Exception:
            pass
        log_file.close()
        self._write_log("Local AI startup timed out")
        raise TimeoutError("Local AI did not become ready in time")

    def _chat_once(
        self,
        profile: AgentProfile,
        messages: list[dict],
        max_tokens: int,
        timeout: int,
        status: Callable[[str], None] | None,
        safe_mode: bool,
    ) -> str:
        self.ensure_started(profile, status=status, safe_mode=safe_mode)
        with self._lock:
            port = self._port
            proc = self._proc
        if not port or not proc or proc.poll() is not None:
            raise RuntimeError("Local AI server is unavailable")
        payload = {
            "model": "local",
            "messages": [{"role": "system", "content": profile.system_prompt}] + messages,
            "temperature": 0.35,
            "max_tokens": max(64, min(int(max_tokens), 256 if not safe_mode else 160)),
            "stream": False,
        }
        if status:
            status("Thinking…")
        r = requests.post(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"].strip()
        if not text:
            raise RuntimeError("Local AI returned an empty response")
        return _strip_reasoning(text)

    def chat(
        self,
        profile: AgentProfile,
        messages: list[dict],
        max_tokens: int,
        timeout: int,
        status: Callable[[str], None] | None = None,
    ) -> str:
        attempts = 2 if self.retry_once else 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            safe_mode = attempt > 0
            try:
                return self._chat_once(
                    profile,
                    messages,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    status=status,
                    safe_mode=safe_mode,
                )
            except (requests.RequestException, OSError, RuntimeError, TimeoutError, KeyError, ValueError) as exc:
                last_error = exc
                self._write_log(f"Chat attempt {attempt + 1} failed: {type(exc).__name__}: {exc}")
                self.stop(wait=True)
                if attempt + 1 < attempts and status:
                    status("AI connection dropped — retrying once in low-memory mode…")
                time.sleep(0.35)
        raise LocalAIError("Local AI could not complete the request. Check Activity for details.") from last_error


def _strip_reasoning(text: str) -> str:
    while "<think>" in text and "</think>" in text:
        a = text.find("<think>")
        b = text.find("</think>", a)
        if b == -1:
            break
        text = (text[:a] + text[b + len("</think>"):]).strip()
    return text.strip()
