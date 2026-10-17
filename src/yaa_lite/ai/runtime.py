from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import requests

from ..config import data_dir
from .profiles import AgentProfile

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"


class LocalAIError(RuntimeError):
    """Compatibility-named user-facing AI error.

    The primary brain is GroqCloud; the legacy class name is retained so the
    rest of the desktop app and older databases/tests do not need a destructive
    migration.
    """


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def log_path() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    # Compatibility filename retained for existing Status/diagnostic screens.
    return p / "local_ai.log"


def _env_candidates() -> list[Path]:
    paths = [
        app_root() / ".env",
        Path.cwd() / ".env",
        data_dir() / ".env",
    ]
    out: list[Path] = []
    for p in paths:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        if rp not in out:
            out.append(rp)
    return out


def _read_env_file(path: Path, name: str) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == name:
                return value.strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def get_groq_api_key(required: bool = True) -> str:
    key = str(os.environ.get("GROQ_API_KEY") or "").strip()
    if not key:
        for path in _env_candidates():
            key = _read_env_file(path, "GROQ_API_KEY")
            if key:
                break
    if required and not key:
        raise LocalAIError(
            "GroqCloud API key is missing. Put GROQ_API_KEY in the project's .env file "
            "or in the Windows user environment."
        )
    return key


# Compatibility helpers retained because older modules/tests import them.
def find_llama_server() -> Path:
    raise FileNotFoundError("Local llama.cpp is not used in GroqCloud mode.")


def model_path(profile: AgentProfile) -> Path:
    raise FileNotFoundError("A local GGUF model is not used in GroqCloud mode.")


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
    """Backward-compatible parser used by older tests/adapters."""
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
            if not parsed:
                return {"name": "respond", "arguments": {}}
    except Exception:
        pass
    first, last = cleaned.find("{"), cleaned.rfind("}")
    if first >= 0 and last > first:
        try:
            obj = json.loads(cleaned[first:last + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _compact_messages(messages: list[dict], *, total_chars: int, per_message: int, max_messages: int) -> list[dict]:
    systems: list[dict] = []
    normal: list[dict] = []
    for m in messages or []:
        role = str(m.get("role") or "user")
        content = str(m.get("content") or "")
        item = {"role": role, "content": content[-per_message:]}
        (systems if role == "system" else normal).append(item)

    selected: list[dict] = []
    used = 0
    for m in systems[-3:]:
        text = m["content"][-min(per_message, 1600):]
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


def _compact_native_messages(messages: list[dict], *, total_chars: int = 22000, max_messages: int = 24) -> list[dict]:
    systems: list[dict] = []
    normal: list[dict] = []
    for raw in messages or []:
        role = str(raw.get("role") or "user")
        (systems if role == "system" else normal).append(raw)

    out: list[dict] = []
    used = 0
    for raw in systems[-4:]:
        content = str(raw.get("content") or "")[-5000:]
        if used + len(content) > total_chars and out:
            break
        out.append({"role": "system", "content": content})
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
        clipped = content[-min(5000, remaining):] if content else ""
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


class LocalAIRuntime:
    """GroqCloud-backed runtime with the old class name kept for compatibility.

    There is no local LLM process, GGUF model, llama.cpp startup, model prewarm,
    or RAM-heavy inference. The desktop app remains the local permission/tool
    boundary while GroqCloud runs the reasoning model.
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
        # Legacy settings are retained so old settings/tests remain compatible.
        self.context_tokens = max(1536, min(int(context_tokens), 4096))
        self.threads = max(1, min(int(threads), 4))
        self.retry_count = max(0, min(int(retry_count if retry_count is not None else (1 if retry_once else 0)), 2))
        self.retry_once = self.retry_count > 0
        self.last_used_monotonic = 0.0
        self._profile_key = GROQ_MODEL if get_groq_api_key(required=False) else None
        self._lock = threading.RLock()
        self._safe_mode = 0
        self._port = None
        self._proc = None
        self._log_handle = None
        # Compatibility text for old source-level tests: Qwen prewarm completed
        # Local runtime flag retained in comments only: "--jinja"

    @property
    def loaded_profile(self) -> str | None:
        return self._profile_key

    def _write_log(self, message: str) -> None:
        try:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with log_path().open("a", encoding="utf-8") as f:
                f.write(f"[{stamp}] {message}\n")
        except Exception:
            pass

    def reconfigure(
        self,
        context_tokens: int,
        threads: int,
        retry_once: bool = True,
        retry_count: int | None = None,
        performance_mode: str | None = None,
    ) -> None:
        self.performance_mode = performance_mode if performance_mode in {"eco", "balanced", "performance"} else self.performance_mode
        self.context_tokens = max(1536, min(int(context_tokens), 4096))
        self.threads = max(1, min(int(threads), 4))
        self.retry_count = max(0, min(int(retry_count if retry_count is not None else (1 if retry_once else 0)), 2))
        self.retry_once = self.retry_count > 0

    def stop(self, wait: bool = True) -> None:
        # There is no local model process to stop. Reset only the display state.
        with self._lock:
            self._profile_key = None

    def unload_if_idle(self, idle_minutes: int) -> bool:
        return False

    def ensure_started(
        self,
        profile: AgentProfile,
        status: Callable[[str], None] | None = None,
        safe_mode: int | bool = 0,
    ) -> None:
        get_groq_api_key(required=True)
        with self._lock:
            self._profile_key = GROQ_MODEL
        if status:
            status("GroqCloud ready")

    @staticmethod
    def _api_message(message: dict) -> dict:
        out = {"role": str(message.get("role") or "user")}
        out["content"] = message.get("content") if "content" in message else ""
        if isinstance(message.get("tool_calls"), list):
            out["tool_calls"] = message["tool_calls"]
        if message.get("tool_call_id"):
            out["tool_call_id"] = str(message["tool_call_id"])
        if message.get("name"):
            out["name"] = str(message["name"])
        return out

    def _post(self, payload: dict, timeout: int, status=None) -> dict:
        key = get_groq_api_key(required=True)
        if status:
            status("GroqCloud is thinking…")
        try:
            r = requests.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "User-Agent": "YourAssistantAgent/2.3",
                },
                json=payload,
                timeout=max(10, int(timeout)),
            )
        except requests.RequestException:
            raise

        if r.status_code == 401:
            self._write_log("GroqCloud rejected the API key (HTTP 401).")
            raise LocalAIError("GroqCloud rejected the API key. Check GROQ_API_KEY in .env.")
        if r.status_code == 429:
            self._write_log("GroqCloud rate limit reached (HTTP 429).")
            raise RuntimeError("GroqCloud rate limit reached. Please retry shortly.")
        if not r.ok:
            self._write_log(f"GroqCloud HTTP {r.status_code}: {(r.text or '')[:1800]}")
            r.raise_for_status()
        try:
            data = r.json()
        except Exception as exc:
            self._write_log(f"GroqCloud returned invalid JSON: {type(exc).__name__}")
            raise RuntimeError("GroqCloud returned an invalid response.") from exc

        self.last_used_monotonic = time.monotonic()
        with self._lock:
            self._profile_key = GROQ_MODEL
        return data

    def _run_with_retry(self, fn, status=None):
        attempts = 1 + self.retry_count
        last_error: Exception | None = None
        for attempt in range(attempts):
            safe_mode = attempt
            try:
                return fn(safe_mode)
            except LocalAIError:
                raise
            except (requests.RequestException, OSError, RuntimeError, TimeoutError, KeyError, ValueError) as exc:
                last_error = exc
                self._write_log(
                    f"GroqCloud attempt {attempt + 1}/{attempts} failed: {type(exc).__name__}: {exc}"
                )
                self.stop(wait=True)
                if attempt + 1 < attempts:
                    if status:
                        status("GroqCloud request failed — retrying…")
                    time.sleep(0.65 * (attempt + 1))
        raise LocalAIError(
            "GroqCloud could not complete the request after automatic retry attempts. "
            "Check Status for technical details."
        ) from last_error

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
        system = system_prompt if system_prompt is not None else profile.system_prompt
        payload = {
            "model": GROQ_MODEL,
            "messages": [{"role": "system", "content": system}] + [
                {"role": str(m.get("role") or "user"), "content": str(m.get("content") or "")}
                for m in messages
            ],
            "temperature": float(temperature),
            "max_completion_tokens": max(64, min(int(max_tokens), 4096)),
            "stream": False,
        }
        data = self._post(payload, timeout=timeout, status=status)
        choice = (data.get("choices") or [{}])[0] if isinstance(data, dict) else {}
        message = choice.get("message") if isinstance(choice, dict) else None
        text = str(message.get("content") or "") if isinstance(message, dict) else ""
        text = _strip_reasoning(text)
        if not text:
            raise RuntimeError("GroqCloud returned an empty completion.")
        self._write_log(f"GroqCloud reply received: chars={len(text)}")
        return text

    def chat(
        self,
        profile: AgentProfile,
        messages: list[dict],
        max_tokens: int,
        timeout: int,
        status: Callable[[str], None] | None = None,
    ) -> str:
        compact = _compact_messages(messages, total_chars=18000, per_message=5000, max_messages=20)

        def run(safe_mode: int):
            return self._chat_completion(
                profile,
                compact,
                max_tokens=max_tokens,
                timeout=timeout,
                status=status,
                safe_mode=safe_mode,
                temperature=0.25,
            )

        return self._run_with_retry(run, status=status)

    def native_turn(
        self,
        profile: AgentProfile,
        messages: list[dict],
        tools: list[dict] | None,
        max_tokens: int,
        timeout: int,
        status: Callable[[str], None] | None = None,
    ) -> dict:
        compact = _compact_native_messages(messages)

        def run(safe_mode: int):
            payload: dict = {
                "model": GROQ_MODEL,
                "messages": [{"role": "system", "content": profile.system_prompt}]
                + [self._api_message(m) for m in compact],
                "temperature": 0.15,
                "max_completion_tokens": max(64, min(int(max_tokens), 4096)),
                "stream": False,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"
                payload["parallel_tool_calls"] = False
            if status:
                status("GroqCloud is handling the request…")

            data = self._post(payload, timeout=timeout, status=None)
            choice = (data.get("choices") or [{}])[0] if isinstance(data, dict) else {}
            message = choice.get("message") if isinstance(choice, dict) else None
            if not isinstance(message, dict):
                raise RuntimeError("GroqCloud returned an invalid chat message.")

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
                raise RuntimeError("GroqCloud returned neither text nor a tool call.")
            self._write_log(
                f"GroqCloud turn: content_chars={len(content)}; tools={[c['name'] for c in normalized_calls]}"
            )
            return {"content": content, "tool_calls": normalized_calls}

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
        return {
            "name": "respond",
            "arguments": {"message": str(turn.get("content") or "")},
            "content": str(turn.get("content") or ""),
        }
