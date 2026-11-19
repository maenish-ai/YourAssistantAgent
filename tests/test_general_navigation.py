"""Generic targets work independently of the optional familiar-site aliases."""
from urllib.parse import parse_qs, urlsplit

import pytest

from yaa_lite.remote.desktop_intent import direct_task, is_desktop_request


@pytest.mark.parametrize('command,expected', [
    ('افتح موقع docs.python.org', 'https://docs.python.org/'),
    ('open site invented-service.example/CaseSensitive?Ref=ABC#Here',
     'https://invented-service.example/CaseSensitive?Ref=ABC#Here'),
    ('إفتح مثال.إختبار/صفحة?Ref=ABC', 'https://xn--mgbh0fb.xn--kgbechtv/صفحة?Ref=ABC'),
    ('فوت على 192.168.10.2:8443/Device', 'https://192.168.10.2:8443/Device'),
    ('open [2001:db8::2]:8443/Status', 'https://[2001:db8::2]:8443/Status'),
    ('افتح متصفح على portal.example/Test', 'https://portal.example/Test'),
    ('open portal.example/download?Action=Copy', 'https://portal.example/download?Action=Copy'),
])
def test_explicit_generic_domains_open_without_inventing_tld_or_changing_path(command, expected):
    assert is_desktop_request(command)
    assert direct_task(command) == ('open_url', {'url': expected})


@pytest.mark.parametrize('command,query', [
    ('افتح موقع متجر جديد', 'متجر جديد'),
    ('open site My Unlisted Service', 'My Unlisted Service'),
    ('ابحث عن MyAPI Version2', 'MyAPI Version2'),
    ('ابحث في الانترنت عن طريقة نسخ ملف', 'طريقة نسخ ملف'),
    ('search the web for Unlisted Product', 'Unlisted Product'),
    ('اعمل سيرش عن معلومات عامة', 'معلومات عامة'),
])
def test_search_and_unknown_site_names_use_complete_owner_query(command, query):
    action, args = direct_task(command)
    assert action == 'open_url' and args['search']
    parsed = urlsplit(args['url'])
    assert parsed.hostname == 'www.google.com'
    assert parse_qs(parsed.query) == {'q': [query]}


@pytest.mark.parametrize('command', [
    'افتح docs.python.org ثم انسخ الملف',
    'open portal.example and move the file',
    'افتح موقع متجر وانقل الملفات',
    'ابحث عن الملف ثم افتح نتيجته',
    'هذا مثال فقط افتح موقع جديد',
    'لا تنفذ افتح example.org',
    'كيف أنسخ الملفات؟',
    'هل افتح المتصفح؟',
])
def test_compound_steps_and_non_commands_are_not_reduced_to_direct_navigation(command):
    assert direct_task(command) is None


@pytest.mark.parametrize('command', [
    'انسخ ملف التقرير إلى المجلد الثاني', 'استخرج الملف المضغوط هنا',
    'سوي مجلد جديد',
    'اعمل فولدر للمشروع', 'غير اسم الملف', 'launch My Installed Editor',
    'copy the selected file', 'extract this archive', 'create a folder',
])
def test_general_file_and_application_requests_reach_planning(command):
    assert is_desktop_request(command)
    assert direct_task(command) is None


@pytest.mark.parametrize('target', ['user@portal.example', 'bad_host.example', 'portal.example:99999',
                                    'javascript:alert(1)', 'data:text/html,test'])
def test_invalid_addresses_never_become_direct_destination(target):
    action = direct_task('open ' + target)
    assert action is None


@pytest.mark.parametrize("titles, expected_focus, expected_reply", [
    (["مستند الدوام", "ملاحظات"], ["0"], "الآن بالمقدمة"),
    (["مستند الدوام", "مستند المصاريف"], [], "أي عنوان تقصد؟"),
    (["ملاحظات"], [], "ما لقيت نافذة"),
])
def test_named_window_focus_uses_observed_ids_without_the_model(titles, expected_focus, expected_reply):
    from threading import Event
    from types import SimpleNamespace
    from yaa_lite.remote.desktop_agent import run_desktop_task

    focused = []
    desktop = SimpleNamespace(
        cancel=Event(),
        list_windows=lambda: {"windows": [
            {"id": str(index), "title": title} for index, title in enumerate(titles)
        ]},
        window_action=lambda identifier, action: (
            focused.append(identifier) or {"ok": action == "focus"}
        ),
    )
    instruction = "رجعني على نافذة مستند"
    assert is_desktop_request(instruction)
    assert expected_reply in run_desktop_task(None, desktop, instruction, lambda message: None)
    assert focused == expected_focus


def test_named_page_uses_existing_browser_bridge_and_returns_verified_url():
    from threading import Event
    from types import SimpleNamespace
    from yaa_lite.remote.desktop_agent import run_desktop_task

    calls = []
    def execute(action, **args):
        calls.append((action, args))
        if action == 'facebook_page_results':
            return {'ok': True, 'tabId': 77,
                    'matches': [{'name': args['name'], 'url': 'https://www.facebook.com/arboretum.example'}]}
        return {'ok': True, 'url': args['url']}

    reply = run_desktop_task(None, SimpleNamespace(cancel=Event()),
        'افتح صفحة نادي الأشجار على الفيسبوك', lambda _: None,
        browser_bridge=SimpleNamespace(connected=True, execute=execute))
    assert [name for name, _ in calls] == ['facebook_page_results', 'open_facebook_page_result']
    assert calls[1][1]['tabId'] == 77
    assert 'نادي الأشجار' in reply and 'https://www.facebook.com/arboretum.example' in reply
