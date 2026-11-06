"""Recognition helpers only; original user text/targets are never rewritten."""
import re
import unicodedata


def normalized_command(text):
    value=unicodedata.normalize('NFKC',str(text or '')).translate(str.maketrans('أإآٱ','اااا'))
    value=re.sub('[\u064b-\u065f\u0670\u0640]','',value)
    return ' '.join(value.split()).strip().lower()


def explicit_example_only(text):
    value=normalized_command(text)
    return bool(re.match(r'^(?:(?:هذا|هاد|هاذ|هاظ)\s+مثال\s+فقط|(?:لا|ما)\s+تنفذ\b|this is (?:only |just )?an example\b|do not execute\b)',value))


def cancel_preview_request(text):
    """Recognize an explicit request to cancel a preview, never a condition."""
    value = normalized_command(text)
    if re.search(r'\b(?:اذا|لو|if|unless)\b', value):
        return False
    if re.search(r'(?:لا|ما|مش|لا\s+اريد)\s+(?:بدي\s+)?(?:تلغي|تلغيه|تلغيها|تلغوا|cancel)', value):
        return False
    return bool(re.search(r'\b(?:الغ|الغي|الغيها|الغيه|الغاء|بلاش|cancel)\b', value))


def immediate_publish_request(text):
    """Detect a positive request to publish now, not a hypothetical or negation."""
    value = normalized_command(text)
    if explicit_example_only(value) or re.search(r'\b(?:اذا|لو|if|unless)\b', value):
        return False
    if re.search(r'(?:لا|ما|مش|ما بدي|لا اريد|do not|dont|don\x27t)\s+.{0,24}(?:نشر|تنشر|انشر|شارك|publish|share|post)', value):
        return False
    action = r'(?:انشر(?:ي|ه|يه)?|شارك(?:ي|ه|يه)?|publish|share|post)'
    now = r'(?:الان|هلا|حالا|فورا|now)'
    return bool(re.search(r'\b'+action+r'\b.{0,100}\b'+now+r'\b|\b'+now+r'\b.{0,60}\b'+action+r'\b', value))
