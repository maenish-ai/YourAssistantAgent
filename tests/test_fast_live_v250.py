from __future__ import annotations

import json

from yaa_lite.fast_live_v250 import fast_facebook_intent, fast_refresh_groups, fast_check_facebook
from yaa_lite.fast_stream_v250 import assemble_stream
from yaa_lite.voice.cloud_service import CloudVoiceService


def _event(delta):
    return 'data: '+json.dumps({'choices':[{'delta':delta}]})


def test_arabic_facebook_fast_routes_only_unambiguous_commands():
    assert fast_facebook_intent('افتح الفيسبوك') == 'open'
    assert fast_facebook_intent('افتح فيسبوك') == 'open'
    assert fast_facebook_intent('حدث المجموعات عندي') == 'refresh'
    assert fast_facebook_intent('افحص حالة الفيس بوك عندي') == 'check'
    assert fast_facebook_intent('انشر إعلاني على فيسبوك') is None
    assert fast_facebook_intent('افتح فيسبوك وانشر الآن') is None


def test_streamed_text_and_tool_calls_stitch_across_chunks():
    parts=[]
    data=[_event({'content':'مرحبا '}),_event({'content':'بك'}),
          _event({'tool_calls':[{'index':0,'id':'call_','function':{'name':'facebook_','arguments':'{"foo":'}}]}),
          _event({'tool_calls':[{'index':0,'id':'22','function':{'name':'status','arguments':'"bar"}'}}]}),
          'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}',
          'data: [DONE]']
    outcome=assemble_stream(data, parts.append)
    assert outcome['content']=='مرحبا بك'
    assert outcome['tool_calls'][0]['name']=='facebook_status'
    assert outcome['tool_calls'][0]['id']=='call_22'
    assert outcome['tool_calls'][0]['arguments']=={'foo':'bar'}
    assert parts[-1]=='مرحبا بك'


def test_fast_discovery_saves_results_and_does_not_fallback_to_slow_browser():
    class Bridge:
        connected=True
        def execute(self,action,**kwargs):
            assert action=='discover_facebook_groups'
            assert kwargs['timeout']<=15
            return {'ok':True,'groups':[
                {'name':'Amman','url':'https://www.facebook.com/groups/1234'},
                {'name':'Bad','url':'https://notfacebook.com/groups/1234'}]}
    class DB:
        def upsert_groups(self,rows):
            assert len(rows)==1
            return 1
    from yaa_lite.agent.facebook_service import FacebookService
    from yaa_lite.config import Settings
    service=FacebookService(DB(),Settings(),activity=lambda *args:None,browser_bridge=Bridge())
    ok,msg,count=fast_refresh_groups(service)
    assert ok and count==1 and service._fb is None


def test_fast_status_does_not_claim_verified_if_only_cached():
    class Bridge:
        connected=False
    from yaa_lite.agent.facebook_service import FacebookActionResult
    class FB:
        browser_bridge=Bridge()
        def status_code(self): return 'connected'
        def verify_session(self):return FacebookActionResult(False,'لم أتأكد من الاتصال الحالي')
        def open_manual_login(self):return FacebookActionResult(True,'فتحت صفحة Facebook')
    text=fast_check_facebook(FB())
    assert 'لم أتأكد' in text and 'فتحت صفحة' in text


def test_voice_models_split_accuracy_and_speed_without_local_download():
    assert CloudVoiceService.STT_MODEL=='whisper-large-v3'
    assert CloudVoiceService.STT_MODEL_LIVE=='whisper-large-v3-turbo'
    assert CloudVoiceService.END_SILENCE <= 0.60
    assert CloudVoiceService.TTS_VOICE_AR=='noura'


def test_live_stt_uses_turbo_and_dictation_uses_accuracy_model(monkeypatch, tmp_path):
    import yaa_lite.voice.cloud_service as module
    monkeypatch.setattr(module, 'get_groq_api_key', lambda required=True: 'fake-test-key')
    captured = []

    def fake_record(self, path, level_callback=None):
        path.write_bytes(b'RIFFfakeWAVEbytes')

    class Response:
        status_code = 200
        ok = True
        def json(self): return {'text': 'افتح فيسبوك'}

    def fake_post(url, headers=None, files=None, data=None, timeout=None, **kwargs):
        captured.append(dict(data))
        return Response()
    monkeypatch.setattr(CloudVoiceService, '_record_wav', fake_record)
    monkeypatch.setattr(module.requests, 'post', fake_post)
    svc = CloudVoiceService(object())
    assert svc.listen_once(mode='live') == 'افتح فيسبوك'
    assert svc.listen_once(mode='dictation') == 'افتح فيسبوك'
    assert [x['model'] for x in captured] == ['whisper-large-v3-turbo', 'whisper-large-v3']
    assert all(x['language']=='ar' for x in captured)


def test_noura_request_uses_documented_groq_fields(monkeypatch):
    import yaa_lite.voice.cloud_service as module
    monkeypatch.setattr(module, 'get_groq_api_key', lambda required=True: 'fake-test-key')
    sent=[]

    class Response:
        status_code=200
        ok=True
        content=b'RIFFfakeaudio'

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        sent.append(json)
        return Response()
    monkeypatch.setattr(module.requests, 'post', fake_post)
    monkeypatch.setattr(CloudVoiceService, '_play_wav_cancelable', lambda self, path: None)
    svc=CloudVoiceService(object())
    assert svc._speak_cloud_arabic('مرحبا، أنا نورا.')
    assert sent[0] == {
        'model':'canopylabs/orpheus-arabic-saudi',
        'voice':'noura',
        'input':'مرحبا، أنا نورا.',
        'response_format':'wav',
    }
