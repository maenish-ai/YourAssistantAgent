from pathlib import Path
import queue
import threading
from types import SimpleNamespace
import pytest
from yaa_lite.fast_live_v250 import fast_facebook_intent
from yaa_lite.ui.native_text import rtl_paragraph,utf16_length


@pytest.mark.parametrize('command',['فوت على الفيسبوك','فوت عالفيسبوك','ادخل على فيسبوك','افتحلي الفيسبوك','إفتح فيسبوك الآن'])
def test_colloquial_open_is_an_actual_open_command(command):
    assert fast_facebook_intent(command)=='open'


def test_examples_and_combined_publishing_requests_do_not_trigger_a_simple_open():
    assert fast_facebook_intent('هذا مثال فقط افحص الفيسبوك') is None
    assert fast_facebook_intent('لا تنفذ، افتح فيسبوك') is None
    assert fast_facebook_intent('افتح فيسبوك وانشر المنشور على الجروبات') is None
    assert fast_facebook_intent('تعرف على الجروبات')=='refresh'


def test_photo_navigation_is_not_mistaken_for_latest_post():
    from yaa_lite.facebook_backend.post_links import canonical_post_url
    assert canonical_post_url('https://www.facebook.com/page/photos/') is None
    assert canonical_post_url('https://www.facebook.com/page/videos/') is None
    assert canonical_post_url('https://notfacebook.com/page/posts/123') is None
    assert canonical_post_url('https://www.facebook.com/photo.php?fbid=123&ref=feed')=='https://www.facebook.com/photo.php?fbid=123'
    assert canonical_post_url('https://www.facebook.com/permalink.php?story_fbid=pfbidABC&id=456&ref=feed')=='https://www.facebook.com/permalink.php?story_fbid=pfbidABC&id=456'
    assert canonical_post_url('https://www.facebook.com/page/posts/pfbidABC?ref=feed')=='https://www.facebook.com/page/posts/pfbidABC'


def test_visible_post_reader_excludes_album_navigation_pins_and_other_pages():
    from yaa_lite.facebook_backend.facebook import FacebookAutomation
    browser=FacebookAutomation();browser.start=lambda:None;browser._check_checkpoint=lambda:None
    rows=[{'url':'https://www.facebook.com/page/photos/','article':None,'pinned':False},
          {'url':'https://www.facebook.com/page/posts/old','article':0,'pinned':True},
          {'url':'https://www.facebook.com/page/videos/123','article':1,'pinned':False},
          {'url':'https://www.facebook.com/page/posts/new','article':1,'pinned':False},
          {'url':'https://www.facebook.com/other/posts/recommendation','article':2,'pinned':False},
          {'url':'https://www.facebook.com/page/posts/second','article':3,'pinned':False}]
    browser.page=SimpleNamespace(goto=lambda *a,**k:None,wait_for_timeout=lambda *a:None,
        locator=lambda *a:SimpleNamespace(evaluate_all=lambda *a:rows),mouse=SimpleNamespace(wheel=lambda *a:None))
    assert browser.find_recent_post_urls('https://www.facebook.com/page',2)==[
        'https://www.facebook.com/page/posts/new','https://www.facebook.com/page/posts/second']


def test_real_installed_controller_opens_facebook_without_model_refusal(tmp_path):
    from yaa_lite.bootstrap import configure_application
    configure_application()
    from yaa_lite.agent.orchestrator import SmartAgentController
    from yaa_lite.agent.facebook_service import FacebookActionResult
    from yaa_lite.ai.engine import ChatEngine
    from yaa_lite.ai.profiles import QWEN
    from yaa_lite.config import Settings
    from yaa_lite.storage.db import ChatDB
    calls=[]
    facebook=SimpleNamespace(open_manual_login=lambda:calls.append('open') or FacebookActionResult(True,'فتحت Facebook'))
    runtime=SimpleNamespace(native_turn=lambda *a,**k:pytest.fail('Simple open must not wait for model routing'))
    db=ChatDB(tmp_path/'db.sqlite');session=db.create_session('hammer')
    controller=SmartAgentController(db,Settings(),ChatEngine(runtime),facebook)
    result=controller.handle(QWEN,[],'فوت عالفيسبوك',session,384,5)
    assert result.used_tools and calls==['open']
    db.set_pending_action(session,'save_facebook_share_rule',{},'old preview')
    result=controller.handle(QWEN,[],'هذا مثال فقط افحص الفيسبوك',session,384,5)
    assert not result.used_tools and calls==['open'] and not db.get_pending_action(session)


def test_same_browser_thread_survives_login_then_discovery_on_another_request(tmp_path,monkeypatch):
    from yaa_lite.agent.facebook_service import FacebookService
    from yaa_lite.config import Settings
    from yaa_lite.storage.db import ChatDB
    visits=[]
    class Browser:
        browser_backend='test-edge'
        def open_interactive(self):visits.append(('open',threading.get_ident()));return 'connected'
        def ensure_logged_in(self):visits.append(('verify',threading.get_ident()))
        def discover_joined_groups(self,limit):
            visits.append(('groups',threading.get_ident()))
            return [{'name':'مجموعة فعلية','url':'https://www.facebook.com/groups/123'}]
        def stop(self):visits.append(('stop',threading.get_ident()))
    service=FacebookService(ChatDB(tmp_path/'db.sqlite'),Settings())
    monkeypatch.setattr(service,'_make_fb',Browser)
    results=[]
    one=threading.Thread(target=lambda:results.append(service.open_manual_login()));one.start();one.join(3)
    two=threading.Thread(target=lambda:results.append(service.discover_groups()));two.start();two.join(3)
    try:
        assert len(results)==2 and all(r.ok for r in results)
        assert results[-1].count==1
        assert not any(name=='stop' for name,_ in visits)
    finally:service.shutdown()
    assert len({thread for _,thread in visits})==1
    assert visits[-1][0]=='stop'


def test_navigation_does_not_interrupt_a_publishing_transaction(tmp_path):
    from yaa_lite.agent.facebook_service import FacebookService
    from yaa_lite.config import Settings
    from yaa_lite.storage.db import ChatDB
    service=FacebookService(ChatDB(tmp_path/'db.sqlite'),Settings())
    service._exec_lock.acquire()
    try:
        assert not service.open_manual_login().ok
        assert not service.discover_groups().ok
        assert service._fb is None
    finally:service._exec_lock.release();service.shutdown()


def test_unicode_helpers_keep_logical_order_and_utf16_caret_units():
    text='افتح Facebook 123 https://example.test 😀'
    assert rtl_paragraph(text)
    assert not rtl_paragraph('https://example.test ثم عربي')
    assert utf16_length(text)==len(text)+1


def test_finish_capture_preserves_all_blocks_instead_of_cancelling(tmp_path):
    import wave
    from yaa_lite.voice.capture_v280 import capture_wav
    finish=threading.Event();reads=[]
    class Stream:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,count):
            reads.append(count)
            if len(reads)==6:finish.set()
            return b'\x2c\x01'*count,False
    device=SimpleNamespace(default=SimpleNamespace(device=(0,0)),
        query_hostapis=lambda:[{'name':'Test'}],query_devices=lambda:[{'name':'Mic','max_input_channels':1,'default_samplerate':8000,'hostapi':0}],
        RawInputStream=lambda **k:Stream())
    output=tmp_path/'voice.wav'
    report=capture_wav(output,SimpleNamespace(voice_input_device='auto'),threading.Event(),finish_event=finish,sd=device)
    assert len(reads)==6 and report.duration==pytest.approx(.3)
    with wave.open(str(output),'rb') as wav:
        assert wav.getframerate()==8000 and wav.getnframes()==sum(reads)


def test_transcription_keeps_arabic_order_and_rejects_silence_hallucinations(tmp_path,monkeypatch):
    from yaa_lite.voice import cloud_service as voice
    monkeypatch.setattr(voice,'get_groq_api_key',lambda required=True:'test-only')
    text='فوت على فيسبوك وشوف الجروبات عندي'
    response={'text':text,'segments':[{'no_speech_prob':.01,'avg_logprob':-.1}]}
    def post(url,**kwargs):
        assert kwargs['data']['language']=='ar' and kwargs['data']['model']=='whisper-large-v3'
        return SimpleNamespace(status_code=200,ok=True,json=lambda:response)
    monkeypatch.setattr(voice.requests,'post',post)
    file=tmp_path/'record.wav';file.write_bytes(b'test audio')
    service=voice.CloudVoiceService(SimpleNamespace())
    assert service.transcribe_file(file)==text
    response['segments']=[{'no_speech_prob':.99,'avg_logprob':-3}]
    with pytest.raises(voice.VoiceError,match='كلام واضح'):service.transcribe_file(file)


def test_finish_dictation_does_not_invalidate_the_final_phrase(tmp_path,monkeypatch):
    import tkinter as tk
    from yaa_lite.bootstrap import configure_application
    configure_application()
    from yaa_lite.ui.chat_window import ChatWindow
    from yaa_lite.config import Settings
    from yaa_lite.storage.db import ChatDB
    from yaa_lite.ui.app import App
    try:root=tk.Tk()
    except tk.TclError:pytest.skip('Tk display unavailable')
    App._styles(root);root.geometry('1200x850');db=ChatDB(tmp_path/'db.sqlite')
    session=db.create_session('hammer')
    monkeypatch.setattr('yaa_lite.ui.chat_window.ChatDB',lambda:db)
    settings=Settings()
    facebook=SimpleNamespace(update_settings=lambda *a:None)
    chat=ChatWindow(root,settings,session,facebook,SimpleNamespace());chat.pack(fill='both',expand=True);root.update()
    try:
        finish=threading.Event();chat._v300_mic_service=SimpleNamespace(finish=finish.set,cancel=lambda:None)
        chat._v300_mic_active=True;generation=chat._v300_mic_generation
        chat._v300_finish_dictation()
        assert finish.is_set() and chat._v300_mic_generation==generation
        chat._v300_mic_queue.put(('text',generation,'آخر جملة بالعربي'))
        chat._v300_mic_queue.put(('done',generation,''))
        chat._v300_poll_dictation();root.update()
        assert chat.input.get('1.0','end-1c')=='آخر جملة بالعربي'
        assert not chat._v300_mic_active
    finally:chat.destroy();root.destroy()
