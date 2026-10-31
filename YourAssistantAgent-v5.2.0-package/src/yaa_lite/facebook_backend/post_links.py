"""Validate real Facebook post permalinks; album/navigation URLs are not posts."""
import re
from urllib.parse import urlsplit,urlunsplit,parse_qs,urlencode


def canonical_post_url(value):
    try:
        parsed=urlsplit(value)
        host=(parsed.hostname or '').lower()
        if parsed.scheme!='https' or not (host=='facebook.com' or host.endswith('.facebook.com')) or parsed.username is not None or parsed.password is not None or parsed.port not in (None,443):return None
        path=parsed.path.rstrip('/')
        query=parse_qs(parsed.query)
        if path in ('/photo.php','/photo'):
            identifier=query.get('fbid',[''])[0]
            if not identifier.isdigit():return None
            return 'https://www.facebook.com/photo.php?'+urlencode({'fbid':identifier})
        if path in ('/permalink.php','/story.php'):
            story=query.get('story_fbid',[''])[0];page=query.get('id',[''])[0]
            if not re.fullmatch('[A-Za-z0-9_]{1,256}',story) or not page.isdigit():return None
            return 'https://www.facebook.com/permalink.php?'+urlencode({'story_fbid':story,'id':page})
        if re.search(r'/(?:posts|videos|reel)/[A-Za-z0-9_-]+$',path):return urlunsplit(('https','www.facebook.com',path,'',''))
        if re.search(r'/photos/(?:a\.[0-9]+/)?[0-9]+$',path):return urlunsplit(('https','www.facebook.com',path,'',''))
    except (TypeError,ValueError):pass
    return None
