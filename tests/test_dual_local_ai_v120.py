from pathlib import Path

from your_assistant_agent.agent_brain import AgentBrain
from your_assistant_agent.local_ai_runtime import (
    LocalAIRuntime,
    LOCAL_AI_PROFILE_ARABIC,
    LOCAL_AI_PROFILE_GENERAL,
)


class DummyDB:
    def __init__(self, settings=None):
        self.settings = settings or {}

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)


class DummySecurity:
    def get_secret(self, key):
        return ""


def test_auto_profile_routes_arabic_to_arabic_model():
    assert LocalAIRuntime.choose_profile("auto", "مرحبا بدي آخر إعلان", "ar") == LOCAL_AI_PROFILE_ARABIC


def test_auto_profile_routes_english_to_general_model():
    assert LocalAIRuntime.choose_profile("auto", "post the latest ad tomorrow", "ar") == LOCAL_AI_PROFILE_GENERAL


def test_forced_profile_is_respected():
    assert LocalAIRuntime.choose_profile("general", "مرحبا", "ar") == LOCAL_AI_PROFILE_GENERAL
    assert LocalAIRuntime.choose_profile("arabic", "hello", "en") == LOCAL_AI_PROFILE_ARABIC


def test_brain_auto_uses_arabic_runtime_for_arabic_text():
    brain = AgentBrain(DummyDB({"local_ai_profile": "auto"}), DummySecurity(), "ar")
    runtime = brain.local_runtime("بدي أنشر على جروبات خلدة")
    assert runtime.profile == LOCAL_AI_PROFILE_ARABIC
    assert runtime.model_path.name == "RightNow-Arabic-0.5B-Turbo-q4_k_m.gguf"


def test_brain_auto_uses_general_runtime_for_english_text():
    brain = AgentBrain(DummyDB({"local_ai_profile": "auto"}), DummySecurity(), "ar")
    runtime = brain.local_runtime("post to the groups tomorrow")
    assert runtime.profile == LOCAL_AI_PROFILE_GENERAL
    assert runtime.model_path.name == "Qwen3-0.6B-Q4_0.gguf"


def test_build_script_pins_arabic_model_and_sha():
    text = (Path(__file__).resolve().parents[1] / "scripts" / "prepare_local_ai.ps1").read_text(encoding="utf-8")
    assert "RightNow-Arabic-0.5B-Turbo-q4_k_m.gguf" in text
    assert "03a58f3cb23af68dbe4247ac2f3f67fdeb8bc3df8bb7e41e0ac0049f8b5211a1" in text
    assert "Qwen3-0.6B-Q4_0.gguf" in text
