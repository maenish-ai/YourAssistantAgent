from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import requests

from .profiles import AgentProfile


def bundle_root() -> Path:
    # PyInstaller one-folder builds place bundled data under sys._MEIPASS
    # (normally dist/YourAssistantAgent/_internal). From source, use repo root.
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


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
    """Runs exactly one llama.cpp server at a time.

    The process is started/stopped outside the GUI thread by callers. No model is
    loaded at application startup; lazy loading avoids the previous UI freeze.
    """

    def __init__(self, context_tokens: int = 1024, threads: int = 2):
        self.context_tokens = max(512, min(int(context_tokens), 2048))
        self.threads = max(1, min(int(threads), 4))
        self._proc: subprocess.Popen | None = None
        self._profile_key: str | None = None
        self._port: int | None = None
        self._lock = threading.RLock()

    @property
    def loaded_profile(self) -> str | None:
        return self._profile_key

    def stop(self) -> None:
        with self._lock:
            proc, self._proc = self._proc, None
            self._profile_key = None
            self._port = None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()

    def ensure_started(self, profile: AgentProfile, status: Callable[[str], None] | None = None) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None and self._profile_key == profile.key:
                return
        self.stop()
        if status:
            status("Loading local AI…")
        server = find_llama_server()
        model = model_path(profile)
        port = _free_port()
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        cmd = [
            str(server),
            "--model", str(model),
            "--host", "127.0.0.1",
            "--port", str(port),
            "--ctx-size", str(self.context_tokens),
            "--threads", str(self.threads),
            "--batch-size", "64",
            "--ubatch-size", "64",
            "--parallel", "1",
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        deadline = time.monotonic() + 45
        url = f"http://127.0.0.1:{port}/health"
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError("Local AI process stopped during startup")
            try:
                r = requests.get(url, timeout=0.8)
                if r.status_code < 500:
                    with self._lock:
                        self._proc = proc
                        self._profile_key = profile.key
                        self._port = port
                    if status:
                        status("Local AI ready")
                    return
            except requests.RequestException:
                pass
            time.sleep(0.25)
        proc.terminate()
        raise TimeoutError("Local AI did not become ready within 45 seconds")

    def chat(self, profile: AgentProfile, messages: list[dict], max_tokens: int, timeout: int,
             status: Callable[[str], None] | None = None) -> str:
        self.ensure_started(profile, status=status)
        with self._lock:
            port = self._port
        if not port:
            raise RuntimeError("Local AI server is unavailable")
        payload = {
            "model": "local",
            "messages": [{"role": "system", "content": profile.system_prompt}] + messages,
            "temperature": 0.35,
            "max_tokens": max(64, min(int(max_tokens), 384)),
            "stream": False,
        }
        if status:
            status("Thinking…")
        r = requests.post(f"http://127.0.0.1:{port}/v1/chat/completions", json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"].strip()
        return _strip_reasoning(text)


def _strip_reasoning(text: str) -> str:
    # Small reasoning models sometimes expose think tags. Keep private working hidden.
    while "<think>" in text and "</think>" in text:
        a = text.find("<think>")
        b = text.find("</think>", a)
        if b == -1:
            break
        text = (text[:a] + text[b + len("</think>"):]).strip()
    return text.strip()
