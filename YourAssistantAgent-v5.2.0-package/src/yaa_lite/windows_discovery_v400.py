"""Local-only, on-demand Windows application discovery. No app launches or cloud calls."""
from __future__ import annotations
import os
import shutil
from pathlib import Path

TOOLS = ('python', 'py', 'git', 'code', 'notepad', 'powershell', 'pwsh', 'winget', 'where', 'cmd')

def _safe_text(value):
    return str(value or '').replace('\x00', '').strip()[:240]

def discover_apps(limit=600):
    """Read Windows uninstall registry, Start Menu shortcuts and PATH tools only."""
    if os.name != 'nt':
        return []
    found = {}
    try:
        import winreg
        roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
        keys = (r'Software\Microsoft\Windows\CurrentVersion\Uninstall',
                r'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')
        for root in roots:
            for path in keys:
                try:
                    handle = winreg.OpenKey(root, path)
                except OSError:
                    continue
                with handle:
                    for i in range(winreg.QueryInfoKey(handle)[0]):
                        try:
                            with winreg.OpenKey(handle, winreg.EnumKey(handle, i)) as sub:
                                name = _safe_text(winreg.QueryValueEx(sub, 'DisplayName')[0])
                                if name:
                                    found.setdefault(name.casefold(), {'name': name, 'source': 'installed', 'kind': 'application'})
                        except (OSError, ValueError):
                            continue
    except ImportError:
        pass
    roots = [Path(os.environ.get('APPDATA', '')) / 'Microsoft/Windows/Start Menu/Programs',
             Path(os.environ.get('PROGRAMDATA', '')) / 'Microsoft/Windows/Start Menu/Programs']
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for file in root.rglob('*.lnk'):
                name = _safe_text(file.stem)
                if name:
                    found.setdefault(name.casefold(), {'name': name, 'source': 'start_menu', 'kind': 'shortcut'})
                if len(found) >= limit:
                    break
        except OSError:
            pass
    for tool in TOOLS:
        if shutil.which(tool):
            found.setdefault(tool.casefold(), {'name': tool, 'source': 'path', 'kind': 'command'})
    return sorted(found.values(), key=lambda x: x['name'].casefold())[:limit]


def describe_apps(apps, limit=35):
    lines = ['البرامج والأدوات المكتشفة محليًا (للمعاينة فقط):', f'العدد: {len(apps)}']
    lines.extend(f"• {app['name']} — {app['source']}" for app in apps[:limit])
    if len(apps) > limit:
        lines.append(f'… و{len(apps)-limit} عنصر إضافي. لا يتم إرسال القائمة للسحابة.')
    lines.append('الاكتشاف لا يمنح صلاحية تشغيل البرامج أو التحكم بها.')
    return '\n'.join(lines)
