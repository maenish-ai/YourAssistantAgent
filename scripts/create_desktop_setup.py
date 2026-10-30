"""Create the private Windows setup file for a relay hosted by a provider."""
import argparse
import getpass
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from yaa_lite.remote.relay_protocol import origin


def create(url,key,destination):
    url=origin(url)
    if not isinstance(key,str) or not 32<=len(key)<=256 or any(c in key for c in '\r\n'):
        raise ValueError('Invalid enrollment key')
    destination=Path(destination)
    with destination.open('x',encoding='utf-8') as output:
        json.dump({'relay_url':url,'enrollment_key':key},output,indent=2)
    try:destination.chmod(0o600)
    except OSError:pass


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',required=True);parser.add_argument('--output',default='desktop-setup.json')
    args=parser.parse_args()
    create(args.url,getpass.getpass('Private RELAY_ENROLLMENT_KEY from your host (hidden): '),args.output)
    print('Created private setup file. Import it into Windows Pair phone. Keep it outside Git.')
