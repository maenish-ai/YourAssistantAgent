"""Small deterministic desktop requests; compound/ambiguous tasks use tool planning."""
import re
from urllib.parse import quote
from ..agent.intent import normalized_command,explicit_example_only


def is_desktop_request(text):
    if explicit_example_only(text):return False
    value=normalized_command(text)
    if value.startswith('/computer '):return True
    if re.match(r'^(اشرح|كيف|ما هي|ما هو|هل|what is|how to)\b',value):return False
    return bool(re.search(r'افتح|فوت|ادخل|شغل|\b(?:اغلق|اغلاق|سكرلي|سكر|تسكر|اقفل|اطلع|اخرج|قفل|صغر|كبر|رجع)\b|تبويب|نافذ|انقل|نقل|ملفات|نزل|واتساب|واتس|whatsapp|متصفح|سطح المكتب|الكمبيوتر|ابحث|سيرش|بحث.*(?:نت|انترنت)|حمل.*(?:ملف|صور)|download|browser|computer|\b(?:open|search|close|minimize|maximize|switch)\b',value))


def direct_task(text):
    raw=str(text).removeprefix('/computer ').strip()
    value=normalized_command(raw)
    opening=r'(?:افتح(?:لي)?|فوت(?:لي)?(?: على)?|ادخل(?: على)?|open)'
    closing=r'(?:اغلق|سكر(?:لي)?|اقفل|اخرج من|اطلع من|close)'
    if re.fullmatch(closing+r' (?:هذا |هاي |الـ)?(?:التبويب|الصفحه|الصفحة|التبويب الحالي|الصفحه الحاليه|الصفحة الحالية|current tab|this tab)',value):
        return ('browser_action',{'action':'close_tab'})
    if re.fullmatch(closing+r' (?:النافذه|النافذة|النافذه الحاليه|النافذة الحالية|هذا البرنامج|current window|this window)',value):
        return ('active_window',{'action':'close'})
    if re.fullmatch(r'(?:صغر|صغرلي|minimize) (?:النافذه|النافذة|النافذه الحاليه|current window)',value):return ('active_window',{'action':'minimize'})
    if re.fullmatch(r'(?:كبر|كبرلي|maximize) (?:النافذه|النافذة|النافذه الحاليه|current window)',value):return ('active_window',{'action':'maximize'})
    if re.fullmatch(opening+r' (?:تبويب جديد|صفحه جديده|صفحة جديدة|new tab)',value):return ('browser_action',{'action':'new_tab'})
    if re.fullmatch(r'(?:اعرض|ورجيني|شوفلي|list|show) (?:النوافذ|البرامج المفتوحه|البرامج المفتوحة|windows|open windows)',value):return ('list_windows',{})
    # Preserve the exact original URL; normalization is for intent only.
    url=re.search(r'https?://\S+',raw,re.I)
    if url and re.fullmatch(opening+r'\s+(?:(?:الرابط|صفحة|الصفحة|صفحه|page|url)\s+)?https?://\S+',value):
        return ('open_url',{'url':url.group(0)})
    # A bare page name is a real web search, never an invented domain.
    query=re.fullmatch(opening+r' (?:صفحة|صفحه|موقع|page|website)\s+(?:اسمها\s+)?(.+)',value)
    if query and not re.search(r'فيسبوك|facebook|وانشر|ثم|وبعدين| and | then |جروب|group',query[1]):
        return ('open_url',{'url':'https://www.google.com/search?q='+quote(query[1]),'search':True})
    return None
