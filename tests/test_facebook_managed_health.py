"""Same-profile browser operations and honest loaded/login/error state."""
from types import SimpleNamespace
import threading

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from yaa_lite.agent.facebook_service import FacebookService
from yaa_lite.config import Settings
from yaa_lite.facebook_backend.facebook import FacebookAutomation, LoginRequired, CheckpointDetected
from yaa_lite.storage.db import ChatDB


class Bridge:
    connected=True
    def execute(self, *args, **kwargs):
        pytest.fail('An active managed profile must not be replaced by an unrelated extension profile')


class Browser:
    browser_backend='test-edge'
    def __init__(self):self.calls=[];self.error=None;self.state='connected'
    def visit(self, label):
        self.calls.append((label,threading.get_ident()))
        if self.error:raise self.error
    def open_interactive(self):self.visit('open');return self.state
    def interactive_status(self):self.visit('status');return self.state
    def connection_status(self):self.visit('status');return self.state
    def ensure_logged_in(self):self.visit('login')
    def search_pages(self,query,limit):self.visit('search');return [{'name':query,'url':'https://www.facebook.com/page'}]
    def find_recent_post_urls(self,source,limit):self.visit('posts');return ['https://www.facebook.com/page/posts/1']
    def discover_joined_groups(self,limit):self.visit('groups');return [{'name':'Actual group','url':'https://www.facebook.com/groups/11'}]
    def stop(self):self.calls.append(('stop',threading.get_ident()))


@pytest.fixture
def stack(tmp_path,monkeypatch):
    browser=Browser();service=FacebookService(ChatDB(tmp_path/'health.sqlite'),Settings(),browser_bridge=Bridge())
    monkeypatch.setattr(service,'_make_fb',lambda:browser)
    yield service,browser
    service.shutdown()


def test_open_reads_groups_preview_and_background_status_share_one_controlled_profile(stack):
    service,browser=stack
    assert service.open_manual_login().ok
    assert service.search_pages('My actual page').ok
    assert service.recent_posts('https://www.facebook.com/page').ok
    assert service.discover_groups().ok
    assert service.preview_campaign('https://www.facebook.com/page')['post_urls']
    assert service.verify_session_background().ok
    assert service.status_code()=='connected'
    assert len({thread for label,thread in browser.calls})==1
    assert [label for label,_ in browser.calls]==['open','search','login','posts','login','groups','login','posts','status']


@pytest.mark.parametrize('operation',['search','posts','preview'])
def test_successful_reads_clear_stale_error_state(stack,operation):
    service,browser=stack
    service._last_status='error'
    service.db.upsert_groups([{'name':'Actual group','url':'https://www.facebook.com/groups/11'}])
    if operation=='search':assert service.search_pages('page').ok
    elif operation=='posts':assert service.recent_posts('https://www.facebook.com/page').ok
    else:assert service.preview_campaign('https://www.facebook.com/page')['post_urls']
    assert service.status_code()=='connected'
    assert 'test-edge' in service.status_text()


@pytest.mark.parametrize('exc,expected',[(LoginRequired('Sign in'),'manual_login'),(CheckpointDetected('Verify'),'verification_required')])
def test_read_auth_failure_is_login_or_verification_not_generic_error(stack,exc,expected):
    service,browser=stack;browser.error=exc
    assert not service.search_pages('page').ok
    assert service.status_code()==expected
    assert not service.recent_posts('https://www.facebook.com/page').ok
    assert service.status_code()==expected


@pytest.mark.parametrize('current,ready,visible,accepted',[
    ('https://www.facebook.com/', 'complete',True,True),
    ('https://www.facebook.com/login/', 'interactive',True,True),
    ('about:blank','complete',True,False),
    ('https://external.example/','complete',True,False),
    ('https://www.facebook.com/','loading',True,False),
    ('https://www.facebook.com/','complete',False,False),
    ('https://www.facebook.com/other','complete',True,False),
])
def test_navigation_timeout_requires_rendered_target_or_auth_redirect(current,ready,visible,accepted):
    def timeout(*a,**k):raise PlaywrightTimeoutError('Navigation timeout')
    browser=FacebookAutomation()
    browser.page=SimpleNamespace(url=current,goto=timeout,evaluate=lambda _:ready,
                                 locator=lambda _:SimpleNamespace(is_visible=lambda **k:visible))
    if accepted:browser._navigate('https://www.facebook.com/')
    else:
        with pytest.raises(PlaywrightTimeoutError):browser._navigate('https://www.facebook.com/')


def test_search_timeout_does_not_accept_previous_search_result():
    def timeout(*a,**k):raise PlaywrightTimeoutError('Navigation timeout')
    browser=FacebookAutomation();browser.page=SimpleNamespace(url='https://www.facebook.com/search/pages/?q=old',goto=timeout,
        evaluate=lambda _:'complete',locator=lambda _:SimpleNamespace(is_visible=lambda **k:True))
    with pytest.raises(PlaywrightTimeoutError):browser._navigate('https://www.facebook.com/search/pages/?q=new')


def test_closed_managed_profile_background_probe_does_not_reopen_it(stack):
    service,browser=stack
    assert service.open_manual_login().ok
    browser.calls.clear();browser.state='browser_closed'
    assert not service.verify_session_background().ok
    assert service.status_code()=='browser_not_connected'
    assert [label for label,_ in browser.calls]==['status']


def test_missing_post_selection_is_not_a_lost_facebook_connection(stack):
    service,browser=stack
    service.db.upsert_groups([{'name':'Actual group','url':'https://www.facebook.com/groups/11'}])
    with pytest.raises(ValueError):service.preview_campaign('https://www.facebook.com/page',post_count=4)
    assert service.status_code()=='connected'


def test_closed_immediately_after_open_is_not_reported_as_success(stack):
    service,browser=stack;browser.state='browser_closed'
    assert not service.open_manual_login().ok
    assert service.status_code()=='browser_not_connected'
    assert not service.open_publishing_login().ok
