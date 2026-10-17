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
from .profiles import AgentProfile, QWEN


class LocalAIError(RuntimeError):
    """User-facing local AI failure. Technical details are written to the AI log."""


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


def _strip_reasoning(text: str) -> str:
    text = str(text or "")
    while "<think>" in text and "</think>" in text:
        a = text.find("<think>")
        b = text.find("</think>", a)
        if b < 0:
            break
        text = (text[:a] + text[b + len("</think>"):]).strip()
    return text.strip()


def _parse_json_object(text: str) -> dict | None:
    """Parse one JSON object from plain, fenced, listed, or lightly wrapped output."""
    cleaned = _strip_reasoning(text).strip()
    if not cleaned:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            if parsed and isinstance(parsed[0], dict):
                return parsed[0]
            # Some tool-tuned models legitimately emit [] when no tool is needed.
            if not parsed:
                return {"name": "respond", "arguments": {}}
    except Exception:
        pass

    # Support wrappers such as <tool_call>{...}</tool_call> or prose around JSON.
    first, last = cleaned.find("{"), cleaned.rfind("}")
    if first >= 0 and last > first:
        try:
            obj = json.loads(cleaned[first:last + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None




def _compact_messages(messages: list[dict], *, total_chars: int, per_message: int, max_messages: int) -> list[dict]:
    """Bound local prompt size while preserving preferences and recent turns."""
    systems: list[dict] = []
    normal: list[dict] = []
    for m in messages or []:
        role = str(m.get("role") or "user")
        content = str(m.get("content") or "")
        item = {"role": role, "content": content[-per_message:]}
        if role == "system":
            systems.append(item)
        else:
            normal.append(item)

    selected: list[dict] = []
    used = 0
    for m in systems[-2:]:
        text = m["content"][-min(per_message, 800):]
        if used + len(text) <= total_chars:
            selected.append({"role": "system", "content": text})
            used += len(text)

    tail: list[dict] = []
    for m in reversed(normal):
        text = m["content"][-per_message:]
        if tail and used + len(text) > total_chars:
            break
        if used + len(text) > total_chars:
            text = text[-max(0, total_chars - used):]
        if not text:
            break
        tail.append({"role": m["role"], "content": text})
        used += len(text)
        if len(tail) >= max_messages:
            break
    selected.extend(reversed(tail))
    return selected

def _compact_native_messages(messages: list[dict], *, total_chars: int = 5600, max_messages: int = 10) -> list[dict]:
    """Compact messages without dropping system context or tool protocol fields."""
    systems: list[dict] = []
    normal: list[dict] = []
    for raw in messages or []:
        role = str(raw.get("role") or "user")
        (systems if role == "system" else normal).append(raw)

    out: list[dict] = []
    used = 0
    for raw in systems[-2:]:
        content = str(raw.get("content") or "")[-900:]
        if used + len(content) > total_chars and out:
            break
        item = {"role": "system", "content": content}
        out.append(item)
        used += len(content)

    tail: list[dict] = []
    slots = max(1, max_messages - len(out))
    for raw in reversed(normal):
        if len(tail) >= slots:
            break
        role = str(raw.get("role") or "user")
        content = str(raw.get("content") or "")
        remaining = max(0, total_chars - used)
        if remaining <= 0 and tail:
            break
        clipped = content[-min(1400, remaining):] if content else ""
        item: dict = {"role": role, "content": clipped}
        if isinstance(raw.get("tool_calls"), list):
            item["tool_calls"] = raw["tool_calls"]
        if raw.get("tool_call_id"):
            item["tool_call_id"] = str(raw["tool_call_id"])
        if raw.get("name"):
            item["name"] = str(raw["name"])
        tail.append(item)
        used += len(clipped)
    out.extend(reversed(tail))
    return out


def _simple_tools(tools: list[dict]) -> list[dict]:
    out: list[dict] = []
    for item in tools or []:
        if not isinstance(item, dict):
            continue
        fn = item.get("function") if item.get("type") == "function" else item
        if not isinstance(fn, dict) or not fn.get("name"):
            continue
        out.append({
            "name": str(fn.get("name")),
            "description": str(fn.get("description") or ""),
            "parameters": fn.get("parameters") if isinstance(fn.get("parameters"), dict) else {
                "type": "object", "properties": {}, "required": []
            },
        })
    return out


class LocalAIRuntime:
    """Long-lived local llama.cpp runtime for Qwen3 on low-memory Windows PCs.

    Qwen handles natural conversation through llama.cpp's normal chat endpoint.
    Tool routing is intentionally performed as a constrained JSON classification
    prompt rather than relying on llama.cpp's model-specific server-side tool
    parser. This makes the desktop app the stable permission/tool boundary.
    """

    def __init__(
        self,
        context_tokens: int = 3072,
        threads: int = 2,
        retry_once: bool = True,
        retry_count: int | None = None,
        performance_mode: str = "balanced",
        prewarm: bool = True,
    ):
        self.performance_mode = performance_mode if performance_mode in {"eco", "balanced", "performance"} else "balanced"
        self.context_tokens = max(1536, min(int(context_tokens), 4096))
        self.threads = max(1, min(int(threads), 4))
        if self.performance_mode == "eco":
            self.context_tokens = min(self.context_tokens, 2048)
            self.threads = 1
        self.retry_count = max(0, min(int(retry_count if retry_count is not None else (1 if retry_once else 0)), 2))
        self.retry_once = self.retry_count > 0
        self.last_used_monotonic = 0.0
        self._proc: subprocess.Popen | None = None
        self._profile_key: str | None = None
        self._port: int | None = None
        self._safe_mode = 0
        self._lock = threading.RLock()
        self._start_lock = threading.Lock()
        self._log_handle = None
        self._prewarm_thread: threading.Thread | None = None

        # The user's main complaint was first-request hangs. If the packaged model
        # and runtime exist, warm Qwen quietly as soon as the app services start.
        if prewarm and self._can_prewarm():
            self._prewarm_thread = threading.Thread(
                target=self._prewarm_worker,
                daemon=True,
                name="yaa-qwen-prewarm",
            )
            self._prewarm_thread.start()

    def _can_prewarm(self) -> bool:
        try:
            find_llama_server()
            model_path(QWEN)
            return True
        except Exception:
            return False

    def _prewarm_worker(self) -> None:
        try:
            self.ensure_started(QWEN)
            self._write_log("Qwen prewarm completed")
        except Exception as exc:
            # Startup must never be blocked by AI warm-up. The normal retry path
            # will show a user-facing error if the first request also fails.
            self._write_log(f"Qwen prewarm failed: {type(exc).__name__}: {exc}")

    @property
    def loaded_profile(self) -> str | None:
        return self._profile_key

    def reconfigure(
        self,
        context_tokens: int,
        threads: int,
        retry_once: bool = True,
        retry_count: int | None = None,
        performance_mode: str | None = None,
    ) -> None:
        new_mode = performance_mode if performance_mode in {"eco", "balanced", "performance"} else self.performance_mode
        new_context = max(1536, min(int(context_tokens), 4096))
        new_threads = max(1, min(int(threads), 4))
        if new_mode == "eco":
            new_context, new_threads = min(new_context, 2048), 1
        new_retries = max(0, min(int(retry_count if retry_count is not None else (1 if retry_once else 0)), 2))
        changed = (new_context, new_threads, new_retries, new_mode) != (
            self.context_tokens, self.threads, self.retry_count, self.performance_mode
        )
        self.context_tokens = new_context
        self.threads = new_threads
        self.performance_mode = new_mode
        self.retry_count = new_retries
        self.retry_once = new_retries > 0
        if changed:
            self.stop(wait=False)
            if self._can_prewarm():
                threading.Thread(target=self._prewarm_worker, daemon=True, name="yaa-qwen-rewarm").start()

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
            self._safe_mode = 0
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

    def _ensure_started_unlocked(
        self,
        profile: AgentProfile,
        status: Callable[[str], None] | None = None,
        safe_mode: int | bool = 0,
    ) -> None:
        level = int(safe_mode)
        with self._lock:
            if (
                self._proc
                and self._proc.poll() is None
                and self._profile_key == profile.model_filename
                and self._safe_mode == level
            ):
                self.last_used_monotonic = time.monotonic()
                return

        self.stop(wait=False)
        if status:
            if level == 0:
                status("Starting Qwen3…")
            elif level == 1:
                status("Restarting Qwen3 in low-memory mode…")
            else:
                status("Restarting Qwen3 in ultra-safe mode…")

        server = find_llama_server()
        model = model_path(profile)
        port = _free_port()
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        ctx = self.context_tokens if level == 0 else (2048 if level == 1 else 1536)
        threads = self.threads if level == 0 else 1
        normal_batch = 12 if self.performance_mode == "eco" else (32 if self.performance_mode == "performance" else 24)
        batch = normal_batch if level == 0 else (12 if level == 1 else 8)
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
            f"Starting Qwen model={profile.model_filename} safe_mode={level} ctx={ctx} threads={threads} batch={batch}"
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

        deadline = time.monotonic() + (85 if level else 70)
        url = f"http://127.0.0.1:{port}/health"
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                log_file.close()
                self._write_log(f"llama-server exited during startup with code {proc.returncode}")
                raise RuntimeError(f"Local AI process stopped during startup (exit {proc.returncode})")
            try:
                r = requests.get(url, timeout=0.9)
                if r.status_code < 500:
                    with self._lock:
                        self._proc = proc
                        self._profile_key = profile.model_filename
                        self._port = port
                        self._safe_mode = level
                        self._log_handle = log_file
                    self.last_used_monotonic = time.monotonic()
                    if status:
                        status("Qwen3 ready")
                    return
            except requests.RequestException:
                pass
            time.sleep(0.3)

        try:
            proc.terminate()
        except Exception:
            pass
        log_file.close()
        self._write_log("Qwen startup timed out")
        raise TimeoutError("Local AI did not become ready in time")

    def ensure_started(
        self,
        profile: AgentProfile,
        status: Callable[[str], None] | None = None,
        safe_mode: int | bool = 0,
    ) -> None:
        # Prewarm and an immediate user request may arrive at the same time.
        # Serialize the whole stop/spawn/health-check sequence so they cannot
        # start competing llama-server processes or kill each other's server.
        with self._start_lock:
            self._ensure_started_unlocked(profile, status=status, safe_mode=safe_mode)

    def _chat_completion(
        self,
        profile: AgentProfile,
        messages: list[dict],
        max_tokens: int,
        timeout: int,
        status: Callable[[str], None] | None,
        safe_mode: int | bool,
        temperature: float = 0.25,
        system_prompt: str | None = None,
    ) -> str:
        self.ensure_started(profile, status=status, safe_mode=safe_mode)
        with self._lock:
            port = self._port
            proc = self._proc
        if not port or not proc or proc.poll() is not None:
            raise RuntimeError("Local AI server is unavailable")

        system = system_prompt if system_prompt is not None else profile.system_prompt
        payload = {
            "model": "local",
            "messages": [{"role": "system", "content": system}] + [
                {"role": str(m.get("role") or "user"), "content": str(m.get("content") or "")}
                for m in messages
            ],
            "temperature": float(temperature),
            "max_tokens": max(64, min(int(max_tokens), 384 if int(safe_mode) == 0 else 224)),
            "stream": False,
        }
        if status:
            status("Qwen3 is thinking…")
        try:
            r = requests.post(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                json=payload,
                timeout=timeout,
            )
            if not r.ok:
                self._write_log(f"Qwen HTTP {r.status_code}: {(r.text or '')[:2000]}")
                r.raise_for_status()
            data = r.json()
        except requests.RequestException:
            code = proc.poll()
            if code is not None:
                self._write_log(f"llama-server stopped during Qwen request with exit code {code}")
            raise

        choice = (data.get("choices") or [{}])[0] if isinstance(data, dict) else {}
        message = choice.get("message") if isinstance(choice, dict) else None
        if isinstance(message, dict):
            text = str(message.get("content") or "")
        else:
            text = str(choice.get("text") or "") if isinstance(choice, dict) else ""
        text = _strip_reasoning(text)
        if not text:
            raise RuntimeError("Qwen returned an empty completion")
        self.last_used_monotonic = time.monotonic()
        self._write_log(f"Qwen raw reply: {text[:1200]}")
        return text

    @staticmethod
    def _api_message(message: dict) -> dict:
        """Preserve OpenAI-compatible chat fields needed by native tool loops."""
        out = {"role": str(message.get("role") or "user")}
        if "content" in message:
            out["content"] = message.get("content")
        else:
            out["content"] = ""
        if isinstance(message.get("tool_calls"), list):
            out["tool_calls"] = message["tool_calls"]
        if message.get("tool_call_id"):
            out["tool_call_id"] = str(message["tool_call_id"])
        if message.get("name"):
            out["name"] = str(message["name"])
        return out

    def native_turn(
        self,
        profile: AgentProfile,
        messages: list[dict],
        tools: list[dict] | None,
        max_tokens: int,
        timeout: int,
        status: Callable[[str], None] | None = None,
    ) -> dict:
        """Run one native Qwen chat/tool turn through llama.cpp.

        Normal conversation returns ``content`` directly. When Qwen needs an
        application capability, llama.cpp parses Qwen's embedded Jinja/Hermes
        tool format and returns OpenAI-style ``tool_calls``. No synthetic
        ``respond`` function is required.
        """
        compact = _compact_native_messages(messages, total_chars=5600, max_messages=10)

        def run(safe_mode: int):
            self.ensure_started(profile, status=status, safe_mode=safe_mode)
            with self._lock:
                port = self._port
                proc = self._proc
            if not port or not proc or proc.poll() is not None:
                raise RuntimeError("Local AI server is unavailable")

            payload: dict = {
                "model": "local",
                "messages": [{"role": "system", "content": profile.system_prompt}] + [self._api_message(m) for m in compact],
                "temperature": 0.15,
                "max_tokens": max(64, min(int(max_tokens), 384 if int(safe_mode) == 0 else 224)),
                "stream": False,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"
                payload["parallel_tool_calls"] = False
            if status:
                status("Qwen3 is handling the request…")

            try:
                r = requests.post(
                    f"http://127.0.0.1:{port}/v1/chat/completions",
                    json=payload,
                    timeout=timeout,
                )
                if not r.ok:
                    self._write_log(f"Qwen native HTTP {r.status_code}: {(r.text or '')[:2000]}")
                    r.raise_for_status()
                data = r.json()
            except requests.RequestException:
                code = proc.poll()
                if code is not None:
                    self._write_log(f"llama-server stopped during native Qwen request with exit code {code}")
                raise

            choice = (data.get("choices") or [{}])[0] if isinstance(data, dict) else {}
            message = choice.get("message") if isinstance(choice, dict) else None
            if not isinstance(message, dict):
                text = _strip_reasoning(str(choice.get("text") or "")) if isinstance(choice, dict) else ""
                if not text:
                    raise RuntimeError("Qwen returned an empty native completion")
                message = {"role": "assistant", "content": text, "tool_calls": []}

            content = _strip_reasoning(str(message.get("content") or "")).strip()
            normalized_calls: list[dict] = []
            for index, call in enumerate(message.get("tool_calls") or []):
                if not isinstance(call, dict):
                    continue
                fn = call.get("function") if isinstance(call.get("function"), dict) else {}
                name = str(fn.get("name") or call.get("name") or "").strip()
                if not name:
                    continue
                raw_args = fn.get("arguments", call.get("arguments", {}))
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args) if raw_args.strip() else {}
                    except Exception:
                        args = {"value": raw_args}
                elif isinstance(raw_args, dict):
                    args = raw_args
                else:
                    args = {}
                call_id = str(call.get("id") or f"call_{index}_{int(time.time()*1000)}")
                normalized_calls.append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(args, ensure_ascii=False, separators=(",", ":")),
                    },
                    "name": name,
                    "arguments": args,
                })

            if not content and not normalized_calls:
                raise RuntimeError("Qwen returned neither text nor a tool call")
            self.last_used_monotonic = time.monotonic()
            self._write_log(
                f"Qwen native turn: content={content[:500]!r}; tools={[c['name'] for c in normalized_calls]}"
            )
            return {"content": content, "tool_calls": normalized_calls}

        return self._run_with_retry(run, status=status)

    def _run_with_retry(self, fn, status=None):
        attempts = 1 + self.retry_count
        last_error: Exception | None = None
        for attempt in range(attempts):
            level = attempt
            try:
                return fn(level)
            except (requests.RequestException, OSError, RuntimeError, TimeoutError, KeyError, ValueError) as exc:
                last_error = exc
                self._write_log(f"AI attempt {attempt + 1}/{attempts} failed: {type(exc).__name__}: {exc}")
                self.stop(wait=True)
                if attempt + 1 < attempts and status:
                    if attempt == 0:
                        status("Qwen3 failed — retrying in low-memory mode…")
                    else:
                        status("Qwen3 failed again — final ultra-safe retry…")
                time.sleep(0.45)
        raise LocalAIError(
            "Qwen3 could not complete the request after automatic restart attempts. Check Status for details."
        ) from last_error

    def unload_if_idle(self, idle_minutes: int) -> bool:
        """Unload the model after an idle period; zero means keep it ready."""
        idle_minutes = max(0, int(idle_minutes))
        if idle_minutes == 0 or not self.loaded_profile or not self.last_used_monotonic:
            return False
        if time.monotonic() - self.last_used_monotonic < idle_minutes * 60:
            return False
        self._write_log(f"Unloading Qwen after {idle_minutes} idle minute(s)")
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
        compact = _compact_messages(messages, total_chars=3800, per_message=1100, max_messages=6)

        def run(safe_mode: int):
            return self._chat_completion(
                profile,
                compact,
                max_tokens=max_tokens,
                timeout=timeout,
                status=status,
                safe_mode=safe_mode,
                temperature=0.28,
            )

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
        """Backward-compatible single-tool adapter over native Qwen tool use."""
        turn = self.native_turn(
            profile, messages, tools=tools, max_tokens=max_tokens, timeout=timeout, status=status
        )
        calls = turn.get("tool_calls") if isinstance(turn.get("tool_calls"), list) else []
        if calls:
            call = calls[0]
            return {
                "name": str(call.get("name") or ""),
                "arguments": call.get("arguments") if isinstance(call.get("arguments"), dict) else {},
                "content": str(turn.get("content") or ""),
            }
        # Native chat text is the normal no-tool response. Keep the old return
        # shape only for legacy callers; the personal-agent path uses content
        # directly and does not expose a synthetic respond tool to Qwen.
        return {
            "name": "respond",
            "arguments": {"message": str(turn.get("content") or "")},
            "content": str(turn.get("content") or ""),
        }

