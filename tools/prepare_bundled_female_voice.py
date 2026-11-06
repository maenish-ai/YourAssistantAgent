#!/usr/bin/env python3
"""Prepare an embedded female Arabic Piper voice for Android (run by Gradle).
Requires: pip install onnx (CI sets it up). Downloads are build-time only.
"""
import hashlib, json, tarfile, urllib.request
from pathlib import Path
import onnx

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'android/app/src/main/assets/voice/arabic-female'
BASE='https://huggingface.co/vadimbelsky/arabic-emirati-female-piper/resolve/f89f1aec8e6486871ffdf8d878c5a39eaf918d60/'
VOICE='arabic-emirati-female-model.onnx'
MODEL_SHA256='1578a9b27d01a0626227225b148179628b770607dd61bdbbc41865bd399106b1'
CONFIG_SHA256='fe31710d91b1d3f7022cc2396d34ad8e2d22cd424cd861409f8c916b86f35049'
ESPEAK_SHA256='4135ccf82e1f40613491c0874d4945ae9e9c7840933d8e25a6f9e003d9ebf533'

def digest(path):
    hasher=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            hasher.update(block)
    return hasher.hexdigest()

def fetch(url,dest,expected_sha256):
    if dest.exists() and digest(dest)==expected_sha256:return
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_suffix(dest.suffix+'.download')
    try:
        with urllib.request.urlopen(url,timeout=120) as response,open(temp,'wb') as f:
            while True:
                block=response.read(1024*1024)
                if not block:break
                f.write(block)
        if digest(temp)!=expected_sha256:raise RuntimeError('Voice dependency SHA-256 mismatch: '+url)
        temp.replace(dest)
    finally:temp.unlink(missing_ok=True)

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    model=DEST/'model.onnx'
    config_file=DEST/'model.onnx.json'
    # Keep the immutable original outside Android assets: conversion modifies
    # ONNX metadata and would invalidate the upstream content hash.
    original=ROOT/'build/voice-cache'/VOICE
    fetch(BASE+VOICE,original,MODEL_SHA256)
    fetch(BASE+VOICE+'.json',config_file,CONFIG_SHA256)
    config=json.loads(config_file.read_text(encoding='utf-8'))
    # The Piper model needs metadata and a phoneme token table for sherpa-onnx.
    tokens=DEST/'tokens.txt'
    tokens.write_text(''.join(f'{s} {ids[0]}\n' for s,ids in config['phoneme_id_map'].items()),encoding='utf-8')
    m=onnx.load(str(original),load_external_data=False)
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
        fetch('https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/espeak-ng-data.tar.bz2',archive,ESPEAK_SHA256)
        with tarfile.open(archive,'r:bz2') as tar:
            for entry in tar.getmembers():
                p=Path(entry.name)
                if p.is_absolute() or '..' in p.parts or p.parts[0]!='espeak-ng-data':
                    raise RuntimeError('Unsafe phonemizer archive')
            tar.extractall(DEST,filter='data')
    if not (data/'phontab').exists():raise RuntimeError('Missing espeak-ng-data/phontab')
    print('Bundled Arabic female voice ready:',model.stat().st_size,'bytes')

if __name__=='__main__':main()
