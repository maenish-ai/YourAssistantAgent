"""Generic computer tools act on observed resources, without example brands."""
import json
import threading
from types import SimpleNamespace

import pytest

from yaa_lite.remote.desktop_agent import run_desktop_task, tools
from yaa_lite.remote.files import RemoteFiles
from yaa_lite.remote.request_router import uses_facebook_tools


def test_file_task_uses_real_file_tool_and_reports_observed_result(tmp_path, monkeypatch):
    (tmp_path/'original.txt').write_text('owner content', encoding='utf-8')
    (tmp_path/'مجموعات').mkdir()
    files=RemoteFiles(tmp_path)
    desktop=SimpleNamespace(cancel=threading.Event(),observe=lambda:{'window':'Explorer','elements':[]})
    class Runtime:
        step=0
        def native_turn(self, profile, messages, **kwargs):
            self.step+=1
            if self.step==1:
                return {'tool_calls':[{'id':'list','name':'list_files','arguments':{'path':'','contains':''}}]}
            result=json.loads(messages[-1]['content'])
            if self.step==2:
                assert {'original.txt','مجموعات'} <= {row['name'] for row in result['entries']}
                return {'tool_calls':[{'id':'copy','name':'copy_file','arguments':{
                    'source':'original.txt','destination_folder':'مجموعات','new_name':''}}]}
            assert result['ok'] and result['path']=='مجموعات/original.txt'
            return {'content':'نسخت الملف إلى المجلد المطلوب'}
    instruction='انسخ original.txt إلى مجلد مجموعات'
    assert not uses_facebook_tools(instruction)
    result=run_desktop_task(Runtime(),desktop,instruction,lambda _:None,files=files)
    assert 'نسخت' in result
    assert (tmp_path/'مجموعات'/'original.txt').read_text()=='owner content'
    assert (tmp_path/'original.txt').exists()


def test_application_task_uses_observed_id_and_rechecks_desktop():
    calls=[]
    desktop=SimpleNamespace(cancel=threading.Event(),
        observe=lambda:calls.append('observe') or {'window':'Requested program','elements':[]},
        list_applications=lambda **kw:{'applications':[{'id':'observed-app','name':'Owner program'}]},
        launch_application=lambda identifier:calls.append(identifier) or {'ok':True,'result':'Launch requested'})
    class Runtime:
        step=0
        def native_turn(self, profile, messages, **kwargs):
            self.step+=1
            if self.step==1:return {'tool_calls':[{'id':'find','name':'list_applications','arguments':{'query':'Owner program','offset':0}}]}
            result=json.loads(messages[-1]['content'])
            if self.step==2:
                assert result['applications'][0]['id']=='observed-app'
                return {'tool_calls':[{'id':'launch','name':'launch_application','arguments':{'id':'observed-app'}}]}
            assert 'observation' in result
            return {'content':'طلبت فتح البرنامج وقرأت النافذة الحالية'}
    run_desktop_task(Runtime(),desktop,'افتح البرنامج المطلوب',lambda _:None)
    assert calls==['observe','observed-app','observe']


def test_general_tools_are_available_independent_of_example_sites():
    names={row['function']['name'] for row in tools()}
    assert {'list_applications','launch_application','create_folder','copy_file','move_file','extract_zip','open_folder'} <= names
