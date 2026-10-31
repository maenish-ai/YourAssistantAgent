"""Conversation and single-use review approvals for the Android companion.

The HTTP transport authenticates the paired device. This service never accepts
shell commands or treats plain text as permission to publish.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from pathlib import Path
import secrets
import threading
import time
from typing import Callable

from ..agent.orchestrator import SmartAgentController
from ..ai.engine import ChatEngine
from ..ai.profiles import QWEN
from ..config import data_dir
from ..github_upload_v430 import (GitHubUploadError, describe_plan,
                                 is_upload_request, prepare_configured_upload, publish_upload)
from ..review_voice_v270 import (execute_reviewed_action, pending_is_fresh,
                                pending_signature)
from ..text_first_v300 import chat_context


@dataclass
class Approval:
    token: str
    kind: str
    payload: object
    signature: str
    expires_at: float


class RemoteAssistant:
    def __init__(self, db, settings, runtime, facebook, publish: Callable,
                 root: Path, activity=None, controller=None):
        self.db, self.settings, self.facebook = db, settings, facebook
        self.runtime = runtime
        from .desktop import WindowsDesktop
        from .files import RemoteFiles
        self.desktop = WindowsDesktop(lambda: bool(getattr(settings,'remote_desktop_enabled',False)))
        self.files = RemoteFiles(Path.home() if getattr(settings,'remote_files_all_drives',False) else (getattr(settings,'remote_files_root','') or Path.home()),
                                 all_drives=getattr(settings,'remote_files_all_drives',False))
        self.publish = publish
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.activity = activity or db.add_activity
        self.controller = controller or SmartAgentController(db, settings, ChatEngine(runtime), facebook)
        self._lock = threading.RLock()
        self._closed = False
        self._approval: Approval | None = None
        self._watching: dict[int, int] = {}
        self._notified: set[int] = set()
        self.session_id = self._load_session()
        # A restart cannot retain a remotely clickable operation.
        self.db.clear_pending_action(self.session_id)
        if hasattr(facebook, 'add_completion_listener'):
            facebook.add_completion_listener(self._completed)

    def _load_session(self) -> int:
        path = self.root / 'conversation.json'
        try:
            identifier = int(json.loads(path.read_text(encoding='utf-8'))['session_id'])
            if self.db.get_session(identifier):
                return identifier
        except (OSError, ValueError, TypeError, KeyError):
            pass
        return self._new_session()

    def _new_session(self) -> int:
        identifier = self.db.create_session('hammer', title='Android')
        path = self.root / 'conversation.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'session_id': identifier}), encoding='utf-8')
        temporary.replace(path)
        return identifier

    def _reply(self, text: str, *, token=None, expires_at=None, session_id=None, clear_approval=False) -> None:
        with self._lock:
            if self._closed:
                return
            text = str(text or '').strip()
            if not text:
                return
            self.db.add_message('assistant', text, 'hammer', session_id or self.session_id)
            # Events carry the complete preview, including every target. Native
            # Android renders it with a scroll view; nothing is truncated here.
            chunks = [text[i:i + 30000] for i in range(0, len(text), 30000)]
            for i, chunk in enumerate(chunks):
                final = i == len(chunks) - 1
                prefix = f'({i + 1}/{len(chunks)})\n' if len(chunks) > 1 else ''
                self.publish(prefix + chunk, approval_token=token if final else None,
                             expires_at=expires_at if final else None,
                             clear_approval=clear_approval and i == 0)

    def _invalidate(self) -> None:
        with self._lock:
            approval, self._approval = self._approval, None
        if approval and approval.kind == 'github':
            Path(approval.payload.archive).unlink(missing_ok=True)
        if approval and not self._closed:
            # Persist the invalidation in the event stream so reconnecting
            # clients do not revive buttons from older replayed previews.
            self.publish('', clear_approval=True)

    def _offer(self, kind: str, payload, signature: str, summary: str) -> None:
        self._invalidate()
        ttl = min(15 * 60, max(60, int(self.settings.approval_timeout_minutes) * 60))
        approval = Approval(secrets.token_urlsafe(24), kind, payload, signature, time.time() + ttl)
        # Publish successfully before exposing any executable approval locally.
        self._reply(summary, token=approval.token, expires_at=approval.expires_at)
        with self._lock:
            if not self._closed:
                self._approval = approval

    def text(self, text: str) -> None:
        if self._closed:
            return
        text = str(text or '').strip()
        if not text:
            return
        if len(text) > 5000:
            self._reply('الرسالة طويلة. أرسل طلباً لا يتجاوز 5000 حرف.')
            return
        from ..agent.intent import explicit_example_only
        if explicit_example_only(text):
            self._invalidate();self.db.clear_pending_action(self.session_id)
            self._reply('فهمت أنه مثال فقط؛ لم أفتح أو أغلق نافذة ولم أجهّز عملية.')
            return
        if text.lower() in {'/new', '/newchat'}:
            self._invalidate()
            self.db.clear_pending_action(self.session_id)
            self.session_id = self._new_session()
            self._reply('بدأت محادثة جديدة. أرسل طلبك أو أرفق ZIP لعرض خطة رفعه.')
            return
        if text.lower() in {'/cancel', 'إلغاء', 'الغاء', 'cancel'}:
            self._invalidate()
            self.db.clear_pending_action(self.session_id)
            self._reply('تم إلغاء المعاينة المعلّقة. العمليات التي بدأت بالفعل تظهر في الحالة.')
            return
        if text.lower() in {'/status', '/start', '/help'}:
            status = self.facebook.current_status()
            self._reply('المساعد متصل.\n'
                        f'Facebook: {status.get("facebook", "غير مفحوص")}\n'
                        f'المهمة: {status.get("step", "idle")} '
                        f'{status.get("done", 0)}/{status.get("total", 0)}\n'
                        'أرسل طلبك أو ZIP. راجع المعاينة واضغط موافق؛ كلمة نعم وحدها لا تنفّذ عملية.\n'
                        'محادثة جديدة: /new — إلغاء المعاينة: /cancel — الحالة: /status')
            return
        from .desktop_intent import is_desktop_request
        desktop_intent = not is_upload_request(text) and is_desktop_request(text)
        if re.search(r'متصفح النشر|publishing.*(?:profile|browser)',text,re.I):desktop_intent=False
        from ..agent.intent import normalized_command
        closing=bool(re.search(r'اغلق|اغلاق|سكر|اقفل|اخرج|اطلع|\bclose\b',normalized_command(text)))
        if desktop_intent and (closing or not re.search(r'جروب|قروب|مجموعات|groups',text,re.I)):
            if not (getattr(self.settings,'remote_desktop_enabled',False) and getattr(self.settings,'remote_ai_enabled',False)):
                self._reply('فعّل التحكم بالكمبيوتر ومساعد الكمبيوتر من إعدادات نسخة Windows أولاً. للتحكم اليدوي استخدم زر سطح المكتب على الهاتف.')
                return
            instruction = text.removeprefix('/computer ').strip()
            if len(instruction)>3000:
                self._reply('اختصر مهمة الكمبيوتر إلى 3000 حرف أو أقل حتى تبقى التعليمات كاملة أثناء التنفيذ.')
                return
            self.db.add_message('user', instruction, 'hammer', self.session_id)
            self.desktop.cancel.clear()
            self._offer('desktop_ai', instruction, instruction,
                'مهمة على الكمبيوتر:\n' + instruction + '\n\nبعد الموافقة ينفّذ المساعد أدوات الكمبيوتر، ويستخدم Groq لتخطيط المهام المركّبة وقراءة تسميات الواجهة. الحد 24 خطوة خلال 3 دقائق. '
                'قد تتضمن الخطوات نقرات وكتابة وفتح صفحات. راقب الشاشة، ويمكنك إيقاف الخطوات التالية من زر إيقاف المهمة. '
                'يمكنك التعامل مع تسجيل دخول المواقع والحفظ من شاشة الهاتف؛ شاشة قفل Windows وUAC خارج الجلسة العادية. هل توافق على هذه المهمة؟')
            return
        with self._lock:
            zip_pending = bool(self._approval and self._approval.kind == 'github')
        if zip_pending and (is_upload_request(text) or text.lower() in {'نعم', 'موافق', 'yes', 'approve'}):
            self._reply('ملف ZIP جاهز في المعاينة السابقة. راجعها واضغط زر موافق؛ الرسالة وحدها لا تنفّذ الرفع.')
            return
        if is_upload_request(text):
            self._reply('اضغط إرفاق ZIP في تطبيق Android. سأعرض الملفات والمستودع والفرع قبل الموافقة على الرفع.')
            return
        # Any new instruction invalidates the old mobile button. A Facebook
        # draft may remain in the DB for natural edits, without authorization.
        self._invalidate()
        self.db.add_message('user', text, 'hammer', self.session_id)
        self.db.rename_session_from_first_message(self.session_id, text)
        try:
            outcome = self.controller.handle(
                QWEN, chat_context(self.db, self.session_id, text), text, self.session_id,
                max(128, min(384, int(self.settings.max_response_tokens))),
                min(120, int(self.settings.ai_timeout_seconds)),
            )
            pending = self.db.get_pending_action(self.session_id)
            if pending_is_fresh(pending):
                summary = str(pending.get('summary') or '')
                self._offer('facebook', None, pending_signature(pending), summary)
            else:
                self._reply(outcome.text)
        except Exception as exc:
            self.activity('remote_request_error', type(exc).__name__)
            self._reply('تعذر إكمال الطلب. افحص اتصال Groq أو تسجيل الدخول إلى المتصفح ثم أعد المحاولة.')

    def document(self, path: Path, caption: str = '') -> None:
        path = Path(path)
        if self._closed:
            path.unlink(missing_ok=True)
            return
        self._invalidate()
        self.db.clear_pending_action(self.session_id)
        try:
            plan = prepare_configured_upload(path, self.settings)
            if not plan.changes and not plan.pending_commit:
                self._reply('ملفات ZIP تطابق المستودع. لم يحدث Commit أو Push جديد.')
                path.unlink(missing_ok=True)
                return
            self.db.add_message('user', 'ZIP received for GitHub review', 'hammer', self.session_id)
            # Include the complete changed-file set. The local dialog can use a
            # compact sample; remote approval needs the full list on the phone.
            files = '\n'.join(f'{item.change}: {item.relative_path}' for item in plan.changes)
            summary = describe_plan(plan) + '\n\nقائمة الملفات الكاملة:\n' + (files or '(retry pending commit)')
            self._offer('github', plan, plan.archive_sha256, summary)
        except (GitHubUploadError, OSError, ValueError) as exc:
            path.unlink(missing_ok=True)
            self._reply('تعذر تجهيز ZIP: ' + str(exc))
        except Exception as exc:
            path.unlink(missing_ok=True)
            self.activity('remote_zip_error', type(exc).__name__)
            self._reply('تعذر فحص الملف. أرسل أرشيف ZIP صالحاً.')

    def callback(self, data: str) -> None:
        action, _, token = str(data or '').partition(':')
        if action not in {'approve', 'cancel'}:
            self._reply('طلب الموافقة غير صالح.')
            return
        with self._lock:
            approval = self._approval
            if (self._closed or not approval or not token or
                    not secrets.compare_digest(approval.token, token)):
                return
            self._approval = None  # consume before touching any external service
        if time.time() > approval.expires_at:
            if approval.kind == 'github':
                Path(approval.payload.archive).unlink(missing_ok=True)
            self._reply('انتهت صلاحية المعاينة. أعد تجهيز العملية.', clear_approval=True)
            return
        if action == 'cancel':
            self.db.clear_pending_action(self.session_id)
            if approval.kind == 'github':
                Path(approval.payload.archive).unlink(missing_ok=True)
            self._reply('تم إلغاء العملية. لم يبدأ التنفيذ.', clear_approval=True)
            return
        self._reply('تمت الموافقة على المعاينة. بدأ التنفيذ…', clear_approval=True)
        if approval.kind == 'github':
            try:
                self._reply(publish_upload(approval.payload, approved=True))
            except GitHubUploadError as exc:
                self._reply('تعذر إكمال الرفع: ' + str(exc))
            except Exception as exc:
                self.activity('remote_publish_error', type(exc).__name__)
                self._reply('تعذر إكمال الرفع. افحص حالة المستودع على الكمبيوتر قبل إعادة الطلب.')
            finally:
                Path(approval.payload.archive).unlink(missing_ok=True)
        elif approval.kind == 'desktop_ai':
            try:
                from .desktop_agent import run_desktop_task
                self.check_desktop()
                if not getattr(self.settings,'remote_ai_enabled',False):raise ValueError('Computer AI is disabled')
                self._reply(run_desktop_task(self.runtime,self.desktop,str(approval.payload),self._reply,
                    files=self.files,offer_download=lambda path,name:self.publish('ملف جاهز للتنزيل: '+name,download_path=path,download_name=name)))
            except Exception as exc:
                self._reply('توقفت مهمة الكمبيوتر: ' + str(exc))
        else:
            try:
                result = execute_reviewed_action(self.controller, self.session_id, approval.signature)
                self._reply(result.text)
                if result.ok and result.data and result.data.get('rule_id') and result.data.get('run_immediately'):
                    identifier = int(result.data['rule_id'])
                    with self._lock:
                        self._watching[identifier] = self.session_id
                    completed = self.facebook.rule_result(identifier)
                    if completed:
                        self._completed(identifier, completed)
            except Exception as exc:
                self.activity('remote_facebook_error', type(exc).__name__)
                self._reply('تعذر بدء المهمة. افحص حالتها قبل إعادة الطلب.')

    def _completed(self, identifier: int, result: dict) -> None:
        with self._lock:
            if self._closed or identifier not in self._watching or identifier in self._notified:
                return
            self._notified.add(identifier)
            origin_session = self._watching.pop(identifier)
        self._reply(f'نتيجة مهمة Facebook #{identifier}: {result.get("status", "unknown")}\n'
                    f'نشر مؤكّد: {result.get("published", 0)}\n'
                    f'أُرسل: {result.get("submitted", 0)}\n'
                    f'بانتظار موافقة الجروب: {result.get("pending_approval", 0)}\n'
                    f'فشل: {result.get("failed", 0)} — تخطّي: {result.get("skipped", 0)}\n'
                    f'الإجمالي: {result.get("total", 0)}' +
                    ('\n' + str(result['error']) if result.get('error') else ''), session_id=origin_session)

    def capabilities(self):
        enabled = bool(getattr(self.settings,'remote_desktop_enabled',False)) and not self._closed
        return {'desktop': enabled and os.name=='nt', 'files': enabled,
                'dictation':not self._closed,'window_control':enabled and os.name=='nt',
                'computer_ai': enabled and bool(getattr(self.settings,'remote_ai_enabled',False)),
                'transfer_limit': 256*1024*1024, 'primary_monitor_only': True,
                'all_drives': bool(getattr(self.settings,'remote_files_all_drives',False)),
                'computer_name': __import__('platform').node(), 'version': __import__('yaa_lite').__version__}

    def check_desktop(self):
        from .desktop import DesktopError
        if self._closed or not getattr(self.settings,'remote_desktop_enabled',False):
            raise DesktopError('التحكم بالكمبيوتر ونقل الملفات غير مفعّل في إعدادات Windows.')

    def desktop_input(self,data):
        self.check_desktop()
        try:self.desktop.input(data)
        except Exception as exc:self._reply('تعذر التحكم: '+str(exc))

    def desktop_control(self,data):
        self.check_desktop()
        try:
            result=self.desktop.window_action(data.get('id'),data.get('action'))
            self._reply(result.get('result','أُرسل إجراء النافذة. راقب الشاشة.'))
        except Exception as exc:self._reply('تعذر التحكم بالنافذة: '+str(exc))

    def dictation(self,path,identifier):
        """Return editable text only; never pass speech directly to text()/tools."""
        path=Path(path)
        try:
            if self._closed:return
            from ..voice.cloud_service import CloudVoiceService
            text=CloudVoiceService(self.settings).transcribe_file(path,mime='audio/mp4')
            if not self._closed:self.publish('',dictation_id=identifier,dictation_text=text[:5000])
        except Exception:
            if not self._closed:self.publish('',dictation_id=identifier,dictation_error='تعذر تفريغ الصوت. تحقق من مفتاح Groq وحدوده والاتصال، ثم أعد التسجيل.')
        finally:path.unlink(missing_ok=True)

    def file_import(self,path,folder,name):
        try:
            self.check_desktop()
            result=self.files.import_file(path,folder,name)
            self._reply('وصل الملف إلى الكمبيوتر: '+result['path'])
        except Exception as exc:self._reply('تعذر نقل الملف: '+str(exc))
        finally:Path(path).unlink(missing_ok=True)

    def stop_desktop_task(self):
        self.desktop.cancel.set()
        with self._lock:
            pending = bool(self._approval and self._approval.kind=='desktop_ai')
        if pending:self._invalidate()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.desktop.close()
        self._invalidate()
        if hasattr(self.facebook, 'remove_completion_listener'):
            self.facebook.remove_completion_listener(self._completed)


def build_remote_worker(settings, security, db, runtime, facebook, activity=None):
    """Build the owner-enabled companion only after the app has been unlocked."""
    if not getattr(settings, 'remote_enabled', False):
        return None
    from .settings import load_remote_token
    from .mobile import MobileServer
    token = load_remote_token(security)
    if not token:
        raise ValueError('Create an Android pairing token in Settings first.')
    root = data_dir() / 'mobile'
    root.mkdir(parents=True, exist_ok=True)
    inbox = root / 'inbox'
    inbox.mkdir(parents=True, exist_ok=True)
    # Unapproved files from earlier runs cannot be executed. Keep recently
    # active files intact while a previous approved job may be finishing.
    for item in inbox.glob('*.zip'):
        if item.is_file() and not item.is_symlink() and time.time() - item.stat().st_mtime > 86400:
            item.unlink(missing_ok=True)
    for item in inbox.glob('*.m4a'):
        if item.is_file() and not item.is_symlink() and time.time()-item.stat().st_mtime>600:item.unlink(missing_ok=True)
    holder = {}
    assistant = RemoteAssistant(db, settings, runtime, facebook,
                                lambda text, **kwargs: holder['server'].publish(text, **kwargs),
                                root, activity=activity)
    try:
        home=getattr(settings,'remote_connection_mode','direct')=='home'
        options={}
        if home:
            from .home import tls_context,endpoint,bind_address
            context,_=tls_context(security)
            public=getattr(settings,'remote_home_public_url','')
            if public:endpoint(public)
            options={'bind':bind_address(),'tls_context':context}
        server = MobileServer(token, assistant, inbox, port=int(settings.remote_home_port if home else settings.remote_port), activity=activity,
                              keep_awake=getattr(settings,'remote_keep_awake',False),**options)
    except Exception:
        assistant.close()
        raise
    holder['server'] = server
    if home:
        from .home import HomeWorker
        return HomeWorker(server)
    if getattr(settings,'remote_connection_mode','direct')=='relay':
        from .relay_bridge import RelayWorker
        from .settings import load_relay_enrollment
        try:
            return RelayWorker(server,settings.remote_relay_url,load_relay_enrollment(security),token,root/'relay')
        except Exception:
            assistant.close()
            raise
    return server
