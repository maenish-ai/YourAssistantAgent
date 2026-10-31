"""Small deterministic desktop requests; compound/ambiguous tasks use tool planning."""
import ipaddress
import re
from urllib.parse import quote, urlsplit, urlunsplit
from ..agent.intent import normalized_command, explicit_example_only


_SITES = {
    'facebook': 'https://www.facebook.com/',
    'فيسبوك': 'https://www.facebook.com/', 'الفيسبوك': 'https://www.facebook.com/',
    'فيس بوك': 'https://www.facebook.com/', 'الفيس بوك': 'https://www.facebook.com/',
    'github': 'https://github.com/', 'جيت هاب': 'https://github.com/',
    'جيتهاب': 'https://github.com/', 'جيت هب': 'https://github.com/', 'الجيت هاب': 'https://github.com/',
    'whatsapp': 'https://web.whatsapp.com/', 'whatsapp web': 'https://web.whatsapp.com/',
    'واتساب': 'https://web.whatsapp.com/', 'واتساب ويب': 'https://web.whatsapp.com/',
    'واتس اب': 'https://web.whatsapp.com/', 'واتس اب ويب': 'https://web.whatsapp.com/',
    'google': 'https://www.google.com/', 'جوجل': 'https://www.google.com/', 'غوغل': 'https://www.google.com/',
    'youtube': 'https://www.youtube.com/', 'يوتيوب': 'https://www.youtube.com/',
    'gmail': 'https://mail.google.com/', 'جيميل': 'https://mail.google.com/',
}
_BROWSER = r'(?:المتصفح|متصفح|البراوزر|براوزر|browser|browser window|edge|ايدج|ايج|chrome|كروم|جوجل كروم|google chrome|microsoft edge)'
_COMPOUND = r'\b(?:ثم|وبعدين|بعدين|وانشر|انشر|شير|شارك|احذف|اضغط|ارفع|حمل|نز[ّل]+|وانقل|انقل|انسخ|واستخرج|استخرج|فك|انشي|انشئ|غير اسم|and|then|publish|share|upload|download|delete|copy|move|rename|extract|click)\b'


def _web_address(target):
    """Accept only a host the owner actually supplied; never append a TLD."""
    if not target or re.search(r'\s|[\\\x00-\x1f]', target) or '://' in target:
        return None
    try:
        parsed = urlsplit('https://' + target)
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            return None
        host = parsed.hostname
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            host = host.encode('idna').decode('ascii').lower()
            labels = host.rstrip('.').split('.')
            if len(host) > 253 or len(labels) < 2 or not all(
                    re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels):
                return None
            if not (re.fullmatch(r'[a-z]{2,63}', labels[-1]) or labels[-1].startswith('xn--')):
                return None
            authority = host
        else:
            authority = '[' + str(address) + ']' if address.version == 6 else str(address)
        if port is not None:
            authority += ':' + str(port)
        return urlunsplit(('https', authority, parsed.path or '/', parsed.query, parsed.fragment))
    except (ValueError, UnicodeError):
        return None


def _navigation_target(target, location):
    """Remove navigation wording while preserving the supplied target text."""
    target = re.sub(r'^(?:على\s+)?(?:صفحة|صفحه|موقع|الصفحه|الصفحة|website|page|site|url|الرابط)\s+', '', target, flags=re.I)
    target = re.sub(r'^' + _BROWSER + r'(?: على ' + location + r')?(?: (?:وفوت|وادخل|وافتح|فوت|ادخل|افتح))?(?: على)?\s+', '', target, flags=re.I)
    target = re.sub(r'\s+(?:على|في|باستخدام|in|using)\s+' + _BROWSER + r'$', '', target, flags=re.I)
    target = re.sub(r'\s+على ' + location + r'$', '', target, flags=re.I)
    return re.sub(r'^(?:صفحة|صفحه|موقع|الصفحه|الصفحة|website|page|site|url|الرابط)\s+', '', target, flags=re.I)


def is_desktop_request(text):
    if explicit_example_only(text):
        return False
    value = normalized_command(text)
    if value.startswith('/computer '):
        return True
    if re.match(r'^(اشرح|كيف|ما هي|ما هو|هل|ليش|لماذا|what is|how to|can you explain|why)\b', value):
        return False
    # Natural follow-ups need the approved-task context and a fresh UI read;
    # route them to planning without guessing which page/window is meant.
    if re.search(r'\b(?:اغلق|اقفل|سكر)(?:ها|ه|هم|هن)\b|\b(?:ارجع|رجعني)\s+(?:له|لها|لهم)\b', value):
        return True
    return bool(re.search(r'افتح|فوت|ادخل|شغل|روح على|\b(?:اغلق|اغلاق|سكرلي|سكر|تسكر|اقفل|اطلع|اخرج|قفل|صغر|كبر|رجع|انسخ|استخرج|انشئ|انشي)\b|(?:فك|غير اسم|اعد تسمية).*?(?:ضغط|ملف|مجلد)|(?:اعمل|سوي|جهز)(?:لي)? (?:مجلد|فولدر|ملف)|تبويب|نافذ|انقل|نقل|ملفات|نزل|واتساب|واتس|whatsapp|متصفح|براوزر|سطح المكتب|الكمبيوتر|ابحث|سيرش|بحث.*(?:نت|انترنت)|حمل.*(?:ملف|صور)|download|browser|computer|\b(?:open|search|close|minimize|maximize|switch|copy|move|rename|extract|unzip|start|launch)\b|\bcreate (?:a |the )?folder\b', value))


def direct_task(text):
    raw = str(text).removeprefix('/computer ').strip()
    if explicit_example_only(raw):
        return None
    value = normalized_command(raw).strip(' .،!؟?')
    opening = r'(?:افتح(?:لي)?|فوت(?:لي)?(?: على)?|ادخل(?: على)?|شغل(?:لي)?|روح على|open|launch)'
    closing = r'(?:اغلق|سكر(?:لي)?|اقفل|اخرج من|اطلع من|close)'
    if re.fullmatch(closing + r' (?:هذا |هاي |الـ)?(?:التبويب|الصفحه|الصفحة|التبويب الحالي|الصفحه الحاليه|الصفحة الحالية|current tab|this tab)', value):
        return ('browser_action', {'action': 'close_tab'})
    if re.fullmatch(closing + r' (?:النافذه|النافذة|النافذه الحاليه|النافذة الحالية|هذا البرنامج|current window|this window)', value):
        return ('active_window', {'action': 'close'})
    if re.fullmatch(r'(?:صغر|صغرلي|minimize) (?:النافذه|النافذة|النافذه الحاليه|current window)', value):
        return ('active_window', {'action': 'minimize'})
    if re.fullmatch(r'(?:كبر|كبرلي|maximize) (?:النافذه|النافذة|النافذه الحاليه|current window)', value):
        return ('active_window', {'action': 'maximize'})
    if re.fullmatch(opening + r' (?:تبويب جديد|صفحه جديده|صفحة جديدة|new tab)', value):
        return ('browser_action', {'action': 'new_tab'})
    if re.fullmatch(r'(?:اعرض|ورجيني|شوفلي|list|show) (?:النوافذ|البرامج المفتوحه|البرامج المفتوحة|windows|open windows)', value):
        return ('list_windows', {})
    # Preserve the exact original URL; normalization is for intent only.
    url = re.search(r'https?://\S+', raw, re.I)
    if url and re.fullmatch(opening + r'\s+(?:(?:الرابط|صفحة|الصفحة|صفحه|page|url)\s+)?https?://\S+', value):
        return ('open_url', {'url': url.group(0)})
    # A requested search is general, not a table of supported site names. Keep
    # the owner's query intact; further executable clauses stay with planning.
    search = re.fullmatch(r'(?:ابحث(?:لي)?(?: في (?:النت|الانترنت))?(?: عن)?|اعمل(?:لي)? (?:بحث|سيرش)(?: عن)?|search(?: the web)?(?: for)?|web search(?: for)?|look up)\s+(.+)', value)
    if search and not re.search(r'\b(?:ثم|وبعدين|بعدين|and then|then)\b', search[1]):
        original_search = re.fullmatch(r'(?:[اأإآ]بحث(?:لي)?(?: في (?:النت|الانترنت))?(?: عن)?|[اأإآ]عمل(?:لي)? (?:بحث|سيرش)(?: عن)?|search(?: the web)?(?: for)?|web search(?: for)?|look up)\s+(.+)', raw, re.I)
        query = original_search[1] if original_search else search[1]
        return ('open_url', {'url': 'https://www.google.com/search?q=' + quote(query), 'search': True})
    target = re.fullmatch(opening + r'\s+(.+)', value)
    if not target:
        return None
    location = r'(?:الديسكتوب|سطح المكتب|الكمبيوتر|الكمبيوتر المكتبي)'
    raw_opening = opening.replace('افتح', '[اأإآ]فتح').replace('ادخل', '[اأإآ]دخل')
    original = re.fullmatch(raw_opening + r'\s+(.+)', raw, re.I)
    original_target = _navigation_target(original[1], location) if original else _navigation_target(target[1], location)
    address = _web_address(original_target)
    if address:
        return ('open_url', {'url': address})
    if re.search(_COMPOUND, target[1]):
        return None
    target = ' '.join(target[1].replace('،', ' ').replace(',', ' ').split())
    if re.fullmatch(_BROWSER + r'(?: على ' + location + r')?', target):
        return ('open_url', {'url': 'https://www.google.com/'})
    # Plain navigation must not depend on Groq or readable accessibility labels.
    # Browser wording describes where to open the site; it does not pick a
    # different browser executable or pretend the app controls that profile.
    target = _navigation_target(target, location)
    if target in _SITES:
        return ('open_url', {'url': _SITES[target]})
    # A named Facebook page opens a real search; it is not a verified page URL.
    page = re.fullmatch(r'(.+?) (?:على|في) (?:الفيسبوك|فيسبوك|الفيس بوك|فيس بوك|facebook)', target)
    if page and not re.search(r'جروب|مجموع|group', page[1]):
        return ('open_url', {'url': 'https://www.facebook.com/search/pages/?q=' + quote(page[1]), 'search': True})
    # A bare page name is a real web search, never an invented domain.
    query = re.fullmatch(opening + r' (?:صفحة|صفحه|موقع|page|website|site)\s+(?:اسمها\s+)?(.+)', value)
    if query and not re.search(r'فيسبوك|facebook|جروب|group', query[1]):
        return ('open_url', {'url': 'https://www.google.com/search?q=' + quote(re.sub(r'^اسمها\s+', '', original_target)), 'search': True})
    return None
