"""Fixed, shareable failure reports: no exception messages or request content."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import secrets
import traceback

import requests

from ..ai.runtime import LocalAIError


MESSAGES = {
    'groq_missing_key': 'مفتاح Groq غير مضبوط على الكمبيوتر. أضفه من إعدادات GroqCloud في نسخة Windows.',
    'groq_auth': 'Groq رفض مفتاح الاتصال. حدّث المفتاح في إعدادات GroqCloud على الكمبيوتر.',
    'groq_rate_limit': 'وصل Groq إلى حد الاستخدام مؤقتاً. انتظر قليلاً ثم أعد الطلب.',
    'groq_network': 'تعذر اتصال الكمبيوتر بخدمة Groq. اتصال الهاتف بالكمبيوتر يعمل؛ افحص إنترنت الكمبيوتر ثم أعد الطلب.',
    'groq_service_unavailable': 'خدمة Groq غير متاحة مؤقتاً. أعد المحاولة لاحقاً.',
    'groq_tool_call': 'Groq لم يُرجع استدعاء أداة صالحاً لإكمال المهمة. أعد الطلب؛ لا تحتاج إعادة اقتران الهاتف.',
    'groq_output_limit': 'توقف رد Groq قبل اكتمال خطة الأدوات. أعد الطلب على خطوات: العثور على الصفحة، قراءة الإعلان، ثم تجهيز المجموعات.',
    'groq_invalid_response': 'وصل رد غير صالح من Groq أثناء تجهيز المهمة. أعد المحاولة؛ إذا تكرر الخطأ أرسل رمز التشخيص.',
    'groq_request_rejected': 'Groq رفض طلب التخطيط. ابدأ محادثة جديدة وأعد الطلب؛ إذا تكرر الخطأ أرسل رمز التشخيص.',
    'facebook_login': 'جلسة فيسبوك تحتاج تسجيل دخول. افتح متصفح النشر من المساعد وأكمل الدخول من زر سطح المكتب على الهاتف، ثم أعد الطلب.',
    'facebook_checkpoint': 'فيسبوك يطلب تحققاً من الحساب. أكمل التحقق في متصفح النشر عبر سطح المكتب على الهاتف، ثم أعد الطلب.',
    'facebook_browser': 'تعذر تنفيذ خطوة في متصفح فيسبوك. افتح متصفح النشر وتحقق من الصفحة من زر سطح المكتب، ثم أعد الطلب.',
    'request_network': 'انقطع اتصال شبكة أثناء تنفيذ خطوة من المهمة. أعد المحاولة؛ اتصال الهاتف وحده لا يثبت اتصال الكمبيوتر بالموقع.',
    'internal_error': 'حدث خطأ برمجي أثناء تجهيز المهمة. أرسل رمز التشخيص من إعدادات الربط لتحديد موضعه؛ إعادة الاقتران ليست مطلوبة لهذا الخطأ.',
}


def failure_report(exc: Exception) -> dict:
    """Classify only typed errors; never infer the cause from free-form text."""
    from ..facebook_backend.facebook import FacebookError, LoginRequired, CheckpointDetected

    if isinstance(exc, LocalAIError):
        code = 'groq_' + str(getattr(exc, 'code', 'invalid_response'))
        if code not in MESSAGES:
            code = 'groq_invalid_response'
    elif isinstance(exc, CheckpointDetected):
        code = 'facebook_checkpoint'
    elif isinstance(exc, LoginRequired):
        code = 'facebook_login'
    elif isinstance(exc, FacebookError):
        code = 'facebook_browser'
    elif isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout, TimeoutError)):
        code = 'request_network'
    else:
        code = 'internal_error'
    root = Path(__file__).resolve().parents[1]
    locations = []
    # Source locations suffice for debugging without disclosing usernames,
    # prompts, headers, page content, exception strings or local variables.
    for frame in traceback.extract_tb(exc.__traceback__):
        try:
            relative = Path(frame.filename).resolve().relative_to(root)
        except ValueError:
            continue
        locations.append(f'{relative.as_posix()}:{frame.lineno}')
    return {'code': code, 'reference': secrets.token_hex(4).upper(),
            'time_utc': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            'stage': 'conversation_tools', 'locations': locations[-8:]}


def failure_message(report: dict) -> str:
    return (MESSAGES[report['code']] + '\n'
            + f"رمز التشخيص: {report['code']} / {report['reference']}")
