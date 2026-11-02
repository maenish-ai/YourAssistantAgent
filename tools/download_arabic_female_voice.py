"""Download the MIT-licensed Arabic Emirati female Piper ONNX model.

Run from the repository root. This prepares model files; Android native
inference integration is a separate requirement.
"""
from pathlib import Path
from urllib.request import urlopen
import argparse
import os
import tempfile

BASE = 'https://huggingface.co/vadimbelsky/arabic-emirati-female-piper/resolve/main/'
FILES = ('arabic-emirati-female-model.onnx', 'arabic-emirati-female-model.onnx.json')


def download(target: Path):
    target.mkdir(parents=True, exist_ok=True)
    for filename in FILES:
        dest = target / filename
        if dest.exists() and dest.stat().st_size > 1024:
            print('Already present:', dest)
            continue
        fd, temporary = tempfile.mkstemp(prefix='voice-', dir=target)
        try:
            with os.fdopen(fd, 'wb') as out, urlopen(BASE + filename, timeout=90) as response:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            if os.stat(temporary).st_size < 1024:
                raise ValueError('Downloaded file unexpectedly small')
            os.replace(temporary, dest)
            print('Downloaded:', dest)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('voice-models/arabic-emirati-female'))
    download(parser.parse_args().output)
