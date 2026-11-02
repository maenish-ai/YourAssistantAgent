#!/usr/bin/env python3
"""Prepare an embedded female Arabic Piper voice for Android (run by Gradle).
Requires: pip install onnx (CI sets it up). Downloads are build-time only.
"""
import json, tarfile, tempfile, urllib.request
from pathlib import Path
import onnx

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'android/app/src/main/assets/voice/arabic-female'
BASE='https://huggingface.co/vadimbelsky/arabic-emirati-female-piper/resolve/main/'
VOICE='arabic-emirati-female-model.onnx'

def fetch(url,dest,min_bytes=100):
    if dest.exists() and dest.stat().st_size>=min_bytes:return
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_suffix(dest.suffix+'.download')
    try:
        with urllib.request.urlopen(url,timeout=120) as response,open(temp,'wb') as f:
            while True:
                block=response.read(1024*1024)
                if not block:break
                f.write(block)
        if temp.stat().st_size<min_bytes:raise RuntimeError('Incomplete download: '+url)
        temp.replace(dest)
    finally:temp.unlink(missing_ok=True)

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    model=DEST/'model.onnx'
    config_file=DEST/'model.onnx.json'
    fetch(BASE+VOICE,model,10_000_000)
    fetch(BASE+VOICE+'.json',config_file,100)
    config=json.loads(config_file.read_text(encoding='utf-8'))
    # The Piper model needs metadata and a phoneme token table for sherpa-onnx.
    tokens=DEST/'tokens.txt'
    tokens.write_text(''.join(f'{s} {ids[0]}\n' for s,ids in config['phoneme_id_map'].items()),encoding='utf-8')
    m=onnx.load(str(model),load_external_data=False)
    if not any(p.key=='comment' and p.value=='piper' for p in m.metadata_props):
        metadata={'model_type':'vits','comment':'piper','language':'Arabic',
                  'voice':config['espeak']['voice'],'has_espeak':'1',
                  'n_speakers':str(config['num_speakers']),
                  'sample_rate':str(config['audio']['sample_rate'])}
        for key,val in metadata.items():
            p=m.metadata_props.add();p.key=key;p.value=str(val)
        onnx.save(m,str(model))
    data=DEST/'espeak-ng-data'
    if not (data/'phontab').exists():
        archive=DEST/'espeak-ng-data.tar.bz2'
        fetch('https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/espeak-ng-data.tar.bz2',archive,10000)
        with tarfile.open(archive,'r:bz2') as tar:
            for entry in tar.getmembers():
                p=Path(entry.name)
                if p.is_absolute() or '..' in p.parts or p.parts[0]!='espeak-ng-data':
                    raise RuntimeError('Unsafe phonemizer archive')
            tar.extractall(DEST,filter='data')
    if not (data/'phontab').exists():raise RuntimeError('Missing espeak-ng-data/phontab')
    print('Bundled Arabic female voice ready:',model.stat().st_size,'bytes')

if __name__=='__main__':main()
