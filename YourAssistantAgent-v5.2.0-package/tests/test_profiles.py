from yaa_lite.ai.profiles import get_profile

def test_profiles():
    assert get_profile("arabic").model_filename.endswith(".gguf")
    assert get_profile("general").key == "general"
