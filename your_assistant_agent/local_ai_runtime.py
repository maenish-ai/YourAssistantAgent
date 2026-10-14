from __future__ import annotations

import atexit
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import requests

from .paths import log_dir


LOCAL_AI_PORT = 11435
LOCAL_AI_HOST = "127.0.0.1"

LOCAL_AI_PROFILE_AUTO = "auto"
LOCAL_AI_PROFILE_GENERAL = "general"
LOCAL_AI_PROFILE_ARABIC = "arabic"

LOCAL_AI_GENERAL_MODEL_NAME = "Qwen3-0.6B-Q4_0"
LOCAL_AI_GENERAL_MODEL_FILE = "Qwen3-0.6B-Q4_0.gguf"
LOCAL_AI_ARABIC_MODEL_NAME = "RightNow-Arabic-0.5B-Turbo-q4_k_m"
LOCAL_AI_ARABIC_MODEL_FILE = "RightNow-Arabic-0.5B-Turbo-q4_k_m.gguf"

# Backward-compatible names used by v1.1 code/tests.
LOCAL_AI_MODEL_NAME = LOCAL_AI_GENERAL_MODEL_NAME
LOCAL_AI_MODEL_FILE = LOCAL_AI_GENERAL_MODEL_FILE


def resource_root() -> Path:
    """Return the PyInstaller/resource root for both source and installed builds."""
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def local_ai_root() -> Path:
    return resource_root() / "assets" / "local_ai"


def bundled_model_path(profile: str = LOCAL_AI_PROFILE_GENERAL) -> Path:
    profile = str(profile or LOCAL_AI_PROFILE_GENERAL).strip().lower()
    filename = LOCAL_AI_ARABIC_MODEL_FILE if profile == LOCAL_AI_PROFILE_ARABIC else LOCAL_AI_GENERAL_MODEL_FILE
    return local_ai_root() / "models" / filename


def bundled_server_path() -> Path:
    exe = "llama-server.exe" if os.name == "nt" else "llama-server"
    return local_ai_root() / "runtime" / exe


class LocalAIRuntimeError(RuntimeError):
    pass


class LocalAIRuntime:
    """Manage one bundled llama.cpp process and one loaded model at a time.

    v1.2 bundles two tiny local models:
    - General: Qwen3-0.6B Q4_0
    - Arabic: RightNow-Arabic-0.5B-Turbo Q4_K_M

    Only one model is resident at once. When the requested profile changes, the
    current llama-server process is stopped before the next model starts. This is
    important for low-memory laptops, especially 4 GB RAM machines.
    """

    _process: subprocess.Popen | None = None
    _process_model_path: Path | None = None
    _lock = threading.RLock()

    def __init__(
        self,
        model_path: str | Path | None = None,
        port: int = LOCAL_AI_PORT,
        profile: str = LOCAL_AI_PROFILE_GENERAL,
    ):
        self.port = int(port)
        self.base_url = f"http://{LOCAL_AI_HOST}:{self.port}"
        requested = str(profile or LOCAL_AI_PROFILE_GENERAL).strip().lower()
        self.profile = requested if requested in {
            LOCAL_AI_PROFILE_GENERAL,
            LOCAL_AI_PROFILE_ARABIC,
        } else LOCAL_AI_PROFILE_GENERAL
        custom = str(model_path or "").strip()
        self.model_path = Path(custom).expanduser() if custom else bundled_model_path(self.profile)
        self.server_path = bundled_server_path()

    @staticmethod
    def contains_arabic(text: str) -> bool:
        return bool(re.search(r"[\u0600-\u06FF]", str(text or "")))

    @classmethod
    def choose_profile(
        cls,
        configured_profile: str,
        text: str = "",
        language_hint: str = "",
    ) -> str:
        configured = str(configured_profile or LOCAL_AI_PROFILE_AUTO).strip().lower()
        if configured in {LOCAL_AI_PROFILE_GENERAL, LOCAL_AI_PROFILE_ARABIC}:
            return configured
        # Auto follows the actual message first. If the message is empty (e.g.
        # a settings test), the UI language is a safe hint.
        if cls.contains_arabic(text):
            return LOCAL_AI_PROFILE_ARABIC
        if not str(text or "").strip() and str(language_hint or "").lower().startswith("ar"):
            return LOCAL_AI_PROFILE_ARABIC
        return LOCAL_AI_PROFILE_GENERAL

    @classmethod
    def bundled_profiles_available(cls) -> dict[str, bool]:
        server_ok = bundled_server_path().is_file()
        return {
            LOCAL_AI_PROFILE_GENERAL: server_ok and bundled_model_path(LOCAL_AI_PROFILE_GENERAL).is_file(),
            LOCAL_AI_PROFILE_ARABIC: server_ok and bundled_model_path(LOCAL_AI_PROFILE_ARABIC).is_file(),
        }

    @property
    def available(self) -> bool:
        return self.server_path.is_file() and self.model_path.is_file()

    @property
    def model_label(self) -> str:
        return self.model_path.stem or (
            LOCAL_AI_ARABIC_MODEL_NAME if self.profile == LOCAL_AI_PROFILE_ARABIC else LOCAL_AI_GENERAL_MODEL_NAME
        )

    def health(self, timeout: float = 1.5) -> bool:
        try:
            r = requests.get(self.base_url + "/health", timeout=timeout)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def _command(self) -> list[str]:
        cpu = os.cpu_count() or 4
        threads = max(2, min(8, cpu // 2 or 2))
        return [
            str(self.server_path),
            "-m", str(self.model_path),
            "--host", LOCAL_AI_HOST,
            "--port", str(self.port),
            "-c", "4096",
            "-t", str(threads),
            "-ngl", "0",
        ]

    @classmethod
    def _stop_process_locked(cls) -> None:
        proc = cls._process
        cls._process = None
        cls._process_model_path = None
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def ensure_started(self, timeout: float = 45.0) -> None:
        requested_path = self.model_path.resolve()
        with self._lock:
            proc = self.__class__._process
            running_path = self.__class__._process_model_path
            same_model_running = (
                proc is not None and proc.poll() is None and running_path == requested_path
            )

        if same_model_running and self.health():
            return

        if not self.available:
            missing = []
            if not self.server_path.is_file():
                missing.append(str(self.server_path))
            if not self.model_path.is_file():
                missing.append(str(self.model_path))
            raise LocalAIRuntimeError("Bundled Local AI files are missing: " + "; ".join(missing))

        with self._lock:
            proc = self.__class__._process
            running_path = self.__class__._process_model_path
            if proc is not None and proc.poll() is None and running_path != requested_path:
                # Never keep two tiny models resident on a low-RAM PC.
                self.__class__._stop_process_locked()

            if self.health() and self.__class__._process_model_path == requested_path:
                return

            proc = self.__class__._process
            if proc is not None and proc.poll() is None:
                pass
            else:
                log_path = log_dir() / "local_ai.log"
                log_handle = open(log_path, "a", encoding="utf-8", errors="replace")
                flags = 0
                startupinfo = None
                if os.name == "nt":
                    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                try:
                    self.__class__._process = subprocess.Popen(
                        self._command(),
                        cwd=str(self.server_path.parent),
                        stdout=log_handle,
                        stderr=subprocess.STDOUT,
                        creationflags=flags,
                        startupinfo=startupinfo,
                    )
                    self.__class__._process_model_path = requested_path
                except OSError as exc:
                    log_handle.close()
                    raise LocalAIRuntimeError(f"Could not start Local AI: {exc}") from exc

        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.health(timeout=1.0):
                return
            proc = self.__class__._process
            if proc is not None and proc.poll() is not None:
                raise LocalAIRuntimeError(f"Local AI process exited with code {proc.returncode}. See local_ai.log")
            time.sleep(0.5)
        raise LocalAIRuntimeError("Local AI took too long to start. See local_ai.log")

    @classmethod
    def stop_global(cls) -> None:
        with cls._lock:
            cls._stop_process_locked()

    @staticmethod
    def _clean_content(text: str) -> str:
        text = str(text or "").strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.I | re.S).strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text).strip()
        return text

    @classmethod
    def extract_json_object(cls, text: str) -> dict[str, Any]:
        text = cls._clean_content(text)
        try:
            value = json.loads(text)
            if isinstance(value, dict):
                return value
        except Exception:
            pass
        decoder = json.JSONDecoder()
        for idx, ch in enumerate(text):
            if ch != "{":
                continue
            try:
                value, _ = decoder.raw_decode(text[idx:])
                if isinstance(value, dict):
                    return value
            except Exception:
                continue
        raise LocalAIRuntimeError("Local AI did not return a readable structured response")

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        max_tokens: int = 1200,
        temperature: float = 0.15,
        timeout: float = 90.0,
    ) -> dict[str, Any]:
        self.ensure_started()
        # /no_think is a Qwen3 control token. Do not inject it into the Arabic
        # Qwen2.5-derived model because it is plain user text there.
        user_content = user_prompt
        if self.profile == LOCAL_AI_PROFILE_GENERAL and "qwen3" in self.model_label.lower():
            user_content = "/no_think\n" + user_prompt
        payload = {
            "model": self.model_label,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
            "stream": False,
        }
        try:
            response = requests.post(
                self.base_url + "/v1/chat/completions",
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
            raise LocalAIRuntimeError(f"Local AI request failed: {exc}") from exc
        return self.extract_json_object(content)

    def test(self) -> tuple[bool, str]:
        try:
            self.ensure_started()
            payload = self.chat_json(
                "Return JSON only. No explanation.",
                'Return exactly this JSON object: {"ok": true, "message": "ready"}',
                max_tokens=80,
                temperature=0.0,
                timeout=45,
            )
            if bool(payload.get("ok")):
                label = "Arabic" if self.profile == LOCAL_AI_PROFILE_ARABIC else "General"
                return True, f"Local AI ready — {label}: {self.model_label}"
            return False, f"Local AI responded but test result was unexpected: {payload}"
        except Exception as exc:
            return False, str(exc)


atexit.register(LocalAIRuntime.stop_global)
