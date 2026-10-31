"""Choose the existing executor by the requested operation, not just 'open'."""
import re

from ..agent.intent import normalized_command


def uses_facebook_tools(text: str) -> bool:
    from ..fast_live_v250 import fast_facebook_intent
    value = normalized_command(text)
    # Folder names and file operations are not Facebook group workflows merely
    # because an owner calls a directory "groups" or mentions a website.
    if re.search(r'مجلد|فولدر|\bfolder\b|\bdirectory\b|انسخ|نسخ|\bcopy\b|انقل|فك الضغط|فك ضغط|استخرج|\bextract\b', value):
        return False
    if fast_facebook_intent(text):
        return True
    if re.search(r'متصفح النشر|publishing.*(?:profile|browser)', value):
        return True
    # A group/post workflow must use the same controlled account as discovery
    # and publishing, even when its first clause asks to open a browser.
    if re.search(r'جروب|قروب|مجموعات|\bgroups?\b', value):
        return True
    if re.search(r'فيس\s*بوك|facebook', value):
        return True
    return bool(re.search(r'انشر|شارك|شير|\bshare\b', value) and
                re.search(r'منشور|بوست|اعلان|صفحه|صفحة|\bpost\b', value))
