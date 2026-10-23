"""Opt-in attachment inspection. No upload, execution, extraction, or Git mutation."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import zipfile

MAX_FILES = 20
MAX_TOTAL = 300 * 1024 * 1024
MAX_TEXT = 12000
KNOWN = {'.txt', '.md', '.py', '.json', '.csv', '.log', '.yaml', '.yml', '.toml', '.ini', '.xml', '.html', '.css', '.js', '.ts'}
MEDIA = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.mp4', '.mov', '.avi', '.mkv', '.webm', '.mp3', '.wav'}


def candidate_repo(name: str, contents: list[str] | None = None) -> str | None:
    names = ' '.join([name, *(contents or [])]).lower().replace('_', '').replace('-', '').replace(' ', '')
    if 'yourassistantagent' in names or 'yaalite' in names:
        return 'maenish-ai/YourAssistantAgent'
    return None


def validate_files(paths: list[str]) -> list[Path]:
    if len(paths) > MAX_FILES:
        raise ValueError(f'Maximum {MAX_FILES} attachments per message')
    result = []
    total = 0
    for name in paths:
        p = Path(name).expanduser().resolve()
        if not p.is_file() or p.is_symlink():
            raise ValueError(f'Not a regular file: {p.name}')
        size = p.stat().st_size
        total += size
        if total > MAX_TOTAL:
            raise ValueError('Total attachments exceed 300 MB')
        result.append(p)
    return result


def inspect_file(path: Path) -> dict:
    p = Path(path)
    size = p.stat().st_size
    result = {'name': p.name, 'type': p.suffix.lower(), 'size': size, 'preview': '', 'repo': None}
    if p.suffix.lower() == '.zip':
        if not zipfile.is_zipfile(p):
            result['preview'] = 'Invalid ZIP'; return result
        with zipfile.ZipFile(p) as z:
            entries = z.infolist()
            names = [i.filename for i in entries[:80]]
            unsafe = any(n.startswith(('/', '\\')) or '..' in n.replace('\\', '/').split('/') or re.match(r'^[A-Za-z]:', n) for n in names)
            result['preview'] = f'ZIP: {len(entries)} entries; sample: {", ".join(names[:15])}'
            if unsafe:
                result['preview'] += '; WARNING: suspicious archive paths'
            result['repo'] = candidate_repo(p.name, names)
    elif p.suffix.lower() in KNOWN and size <= 2 * 1024 * 1024:
        with p.open('r', encoding='utf-8', errors='replace') as f:
            result['preview'] = f.read(MAX_TEXT)
        result['repo'] = candidate_repo(p.name, [result['preview'][:1000]])
    elif p.suffix.lower() in MEDIA:
        result['preview'] = 'Media attached (metadata only; content is not analyzed by this module).'
        result['repo'] = candidate_repo(p.name)
    else:
        result['preview'] = 'Attached (binary/unsupported format; no content interpretation).'
        result['repo'] = candidate_repo(p.name)
    return result


def inspect_files(paths: list[str]) -> list[dict]:
    return [inspect_file(p) for p in validate_files(paths)]


def summary(items: list[dict], include_content: bool = False) -> str:
    lines = ['Attachment inspection (local, no file was uploaded or modified):']
    for item in items:
        lines.append(f'- {item["name"]} ({item["size"]} bytes, {item["type"]})')
        if item['repo']:
            lines.append(f'  Suggested repository: {item["repo"]} (NOT confirmed; ask before any changes)')
        if include_content:
            lines.append('  Preview: ' + item['preview'][:MAX_TEXT])
    return '\n'.join(lines)
