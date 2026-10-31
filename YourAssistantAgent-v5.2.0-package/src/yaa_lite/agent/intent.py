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
