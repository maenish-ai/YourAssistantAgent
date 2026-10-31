from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

MODEL_ID = "openai/gpt-oss-120b"
API_URL = "https://api.groq.com/openai/v1/models"

def load_env_key() -> str:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        raise RuntimeError(".env file was not found next to this test file.")
    for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == "GROQ_API_KEY":
            key = value.strip().strip('"').strip("'")
            if key:
                return key
    raise RuntimeError("GROQ_API_KEY was not found in .env.")

def main() -> int:
    try:
        key = load_env_key()
        req = urllib.request.Request(
            API_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
                "User-Agent": "YourAssistantAgent-Groq-Test/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))

        ids = {
            str(item.get("id"))
            for item in (data.get("data") or [])
            if isinstance(item, dict) and item.get("id")
        }

        print("GROQ_API_KEY: found")
        print("GroqCloud connection: OK")
        print(f"{MODEL_ID}: {'available' if MODEL_ID in ids else 'not listed'}")
        return 0

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"GroqCloud HTTP error: {exc.code}")
        if exc.code == 401:
            print("The API key was rejected. Check the key in .env.")
        else:
            print(body[:500])
        return 2
    except Exception as exc:
        print(f"Test failed: {type(exc).__name__}: {exc}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
