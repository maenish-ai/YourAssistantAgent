"""Generate deployment files without printing credentials into terminal logs."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets


def configure(directory,domain):
    domain=domain.strip().lower()
    if not re.fullmatch(r'(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}',domain) or '..' in domain:
        raise ValueError('Use your public domain name without https:// or a path')
    directory=Path(directory)
    env=directory/'.env';setup=directory/'desktop-setup.json'
    if env.exists() or setup.exists():raise ValueError('Configuration already exists. Preserve it; do not rotate keys by overwriting it.')
    key=secrets.token_urlsafe(48)
    for path,content in [(env,'PUBLIC_HOST='+domain+'\nRELAY_ENROLLMENT_KEY='+key+'\n'),
                         (setup,json.dumps({'relay_url':'https://'+domain,'enrollment_key':key},indent=2))]:
        with path.open('x',encoding='utf-8') as output:output.write(content)
        try:os.chmod(path,0o600)
        except OSError:pass
    return setup

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--domain',required=True)
    args=parser.parse_args();configure(Path(__file__).parent,args.domain)
    print('Created .env and desktop-setup.json. Keep both private. Import desktop-setup.json into the Windows app.')
