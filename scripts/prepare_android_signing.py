"""Create a durable Android release key without printing passwords or key bytes."""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess


def prepare(directory, keytool=None):
    directory=Path(directory)
    if directory.exists(): raise ValueError('Destination exists. Keep the previous signing key; never overwrite it.')
    keytool=keytool or shutil.which('keytool')
    if not keytool: raise ValueError('Install Java 17 and make keytool available first.')
    directory.mkdir(parents=True,mode=0o700)
    password=secrets.token_urlsafe(36)
    environment={**os.environ,'YAA_NEW_SIGNING_PASSWORD':password}
    key=directory/'yourassistant-release.jks'
    subprocess.run([str(keytool),'-genkeypair','-keystore',str(key),'-storetype','PKCS12',
                    '-storepass:env','YAA_NEW_SIGNING_PASSWORD','-keypass:env','YAA_NEW_SIGNING_PASSWORD',
                    '-alias','yourassistant','-keyalg','RSA','-keysize','3072','-validity','10000',
                    '-dname','CN=Your Assistant Agent, O=Your Assistant Agent','-noprompt'],
                   env=environment,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    values={'ANDROID_KEYSTORE_BASE64':base64.b64encode(key.read_bytes()).decode(),
            'ANDROID_STORE_PASSWORD':password,'ANDROID_KEY_ALIAS':'yourassistant','ANDROID_KEY_PASSWORD':password}
    destination=directory/'github-secrets.json'
    with destination.open('x',encoding='utf-8') as output:json.dump(values,output,indent=2)
    for path in (key,destination):
        try:path.chmod(0o600)
        except OSError:pass
    (directory/'READ_ME_PRIVATE_AR.txt').write_text(
        'هذا مجلد خاص بمفتاح توقيع Android. احتفظ به خارج المستودع مع نسخة احتياطية.\n'
        'لا ترفع هذه الملفات أو github-secrets.json إلى GitHub كملفات مصدر.\n'
        'في GitHub افتح Settings > Secrets and variables > Actions وأضف القيم الأربع من github-secrets.json كـ Repository secrets.\n'
        'بعدها يبني workflow نسخة Release بالمفتاح نفسه في كل تحديث. لا تغيّر المفتاح: Android يرفض التحديث بمفتاح مختلف.\n'
        'إذا كنت تستخدم نسخة Debug القديمة، يلزم حذفها مرة واحدة قبل تثبيت أول Release. حذف التطبيق يزيل اقترانه المحفوظ، ثم يمكن مسح QR مجدداً.\n',encoding='utf-8')
    return directory


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--directory',default='android-signing-private');parser.add_argument('--keytool')
    options=parser.parse_args();prepare(options.directory,options.keytool)
    print('Private signing files created. Keep them outside Git. Read READ_ME_PRIVATE_AR.txt.')
