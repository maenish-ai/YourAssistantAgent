"""Real desktop routing with fake Windows boundaries; no model/account required."""
from contextlib import contextmanager
from types import SimpleNamespace
import threading
from urllib.parse import parse_qs, urlsplit

import pytest

from yaa_lite.remote.desktop import DesktopError, WindowsDesktop
from yaa_lite.remote.desktop_agent import run_desktop_task
from yaa_lite.remote.desktop_intent import direct_task, is_desktop_request


@pytest.mark.parametrize('instruction,url', [
    ('افتح فيسبوك', 'https://www.facebook.com/'),
    ('فوت على الفيس بوك', 'https://www.facebook.com/'),
    ('افتح GitHub', 'https://github.com/'),
    ('افتح موقع جيت هاب', 'https://github.com/'),
    ('افتح براوزر على الديسكتوب', 'https://www.google.com/'),
    ('افتح متصفح على الفيسبوك', 'https://www.facebook.com/'),
    ('افتح براوزر على الديسكتوب وفوت على فيسبوك', 'https://www.facebook.com/'),
    ('افتح براوزر على الديسكتوب، فوت على فيسبوك', 'https://www.facebook.com/'),
    ('افتح فيسبوك على الكمبيوتر', 'https://www.facebook.com/'),
    ('افتح متصفح على الكمبيوتر وافتح موقع فيسبوك', 'https://www.facebook.com/'),
    ('افتح واتساب ويب', 'https://web.whatsapp.com/'),
    ('فوت على github في المتصفح', 'https://github.com/'),
])
def test_site_and_browser_open_do_not_require_model_or_accessibility(instruction, url):
    calls=[]
    desktop=SimpleNamespace(cancel=threading.Event(),
        open_url=lambda value:calls.append(value) or {'ok':True,'result':'Opening requested'})
    assert is_desktop_request(instruction)
    assert run_desktop_task(None, desktop, instruction, lambda _:None)=='Opening requested'
    assert calls==[url]


def test_named_facebook_page_is_search_not_invented_page_address():
    name='اسم صفحة تجريبية'
    action,args=direct_task('افتح صفحة '+name+' على الفيسبوك')
    assert action=='open_url' and args['search']
    parsed=urlsplit(args['url'])
    assert parsed.hostname=='www.facebook.com' and parsed.path=='/search/pages/'
    assert parse_qs(parsed.query)=={'q':[name]}


@pytest.mark.parametrize('instruction',[
    'افتح فيسبوك وانشر آخر إعلان على المجموعات',
    'افتح GitHub ثم ارفع الملفات',
    'افتح صفحة تجريبية على الفيسبوك وبعدين شارك المنشور',
    'هذا مثال فقط افتح فيسبوك',
])
def test_compound_mutations_and_examples_are_never_reduced_to_open_only(instruction):
    assert direct_task(instruction) is None


@pytest.mark.parametrize('instruction', ['أغلقها', 'سكرها', 'افتحها', 'ارجع لها', 'سكّرهم لو سمحت'])
def test_pronoun_followups_route_to_observed_planning_without_inventing_target(instruction):
    assert is_desktop_request(instruction)
    assert direct_task(instruction) is None


def test_only_visible_browser_can_be_selected_when_assistant_is_foreground(monkeypatch):
    desktop=WindowsDesktop(lambda:True)
    browser=SimpleNamespace(is_visible=lambda:True,process_id=lambda:123)
    desktop._windows={'observed':(browser,123,__import__('time').monotonic(),'msedge.exe')}
    monkeypatch.setattr(desktop,'list_windows',lambda:{'windows':[
        {'id':'observed','active':False,'process':'msedge.exe'},
    ]})
    assert desktop._browser_window('',None)==(browser,123)
    monkeypatch.setattr(desktop,'list_windows',lambda:{'windows':[
        {'id':'one','active':False,'process':'msedge.exe'},
        {'id':'two','active':False,'process':'chrome.exe'},
    ]})
    with pytest.raises(DesktopError,match='عدة نوافذ'):
        desktop._browser_window('',None)


def test_model_cannot_report_success_after_an_action_failure():
    desktop=SimpleNamespace(cancel=threading.Event(),observe=lambda:{'elements':[]},
        click_element=lambda _: (_ for _ in ()).throw(DesktopError('العنصر تغيّر')))
    class Runtime:
        step=0
        def native_turn(self,*args,**kwargs):
            self.step+=1
            if self.step==1:return {'tool_calls':[{'id':'click','name':'click_element','arguments':{'id':'missing'}}]}
            return {'content':'نجحت العملية'}
    result=run_desktop_task(Runtime(),desktop,'اختر العنصر',lambda _:None)
    assert 'لم تكتمل' in result and 'العنصر تغيّر' in result
    assert 'نجحت العملية' not in result


def test_followup_context_is_bounded_and_not_additional_authorization(monkeypatch):
    desktop=SimpleNamespace(cancel=threading.Event(),observe=lambda:{'elements':[]})
    class Runtime:
        def native_turn(self,profile,messages,**kwargs):
            text=str(messages)
            assert 'Previous owner-approved tasks' in text and 'NOT authorization' in text
            assert 'افتح الصفحة المطلوبة' in text and 'أغلقها' in text
            assert 'very-old' not in text
            return {'content':'حدد أي صفحة تقصد قبل الإغلاق.'}
    history=[{'instruction':'very-old','result':'old'}]+[
        {'instruction':'افتح الصفحة المطلوبة','result':'طلب فتح الرابط أرسل'} for _ in range(4)]
    assert 'حدد' in run_desktop_task(Runtime(),desktop,'أغلقها',lambda _:None,history=history)
