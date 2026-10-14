from __future__ import annotations

import os
import socket
import subprocess
from datetime import datetime, timedelta


def normalize_mac(mac: str) -> str:
    value = ''.join(ch for ch in (mac or '') if ch.isalnum()).upper()
    if len(value) != 12 or any(ch not in '0123456789ABCDEF' for ch in value):
        raise ValueError('Invalid MAC address')
    return value


def build_magic_packet(mac: str) -> bytes:
    raw = bytes.fromhex(normalize_mac(mac))
    return b'\xff' * 6 + raw * 16


def send_magic_packet(mac: str, broadcast_ip: str = '255.255.255.255', port: int = 9) -> None:
    packet = build_magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast_ip or '255.255.255.255', int(port or 9)))


def schedule_windows_wake(when: datetime, minutes_early: int = 2, task_name: str = 'YourAssistantAgentWake') -> tuple[bool, str]:
    """Schedule a one-shot Windows task with WakeToRun.

    The task itself only runs cmd /c exit; its purpose is to wake the machine.
    This must be called while Windows is awake, before it goes to sleep.
    """
    if os.name != 'nt':
        return False, 'Windows wake scheduling is only available on Windows.'
    target = when - timedelta(minutes=max(0, int(minutes_early)))
    if target <= datetime.now():
        target = when
    iso = target.replace(microsecond=0).isoformat()
    script = (
        "$ErrorActionPreference='Stop';"
        f"$t=[datetime]::Parse('{iso}');"
        "$a=New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c exit 0';"
        "$tr=New-ScheduledTaskTrigger -Once -At $t;"
        "$s=New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries;"
        f"Register-ScheduledTask -TaskName '{task_name}' -Action $a -Trigger $tr -Settings $s -Force | Out-Null;"
        "Write-Output $t.ToString('s')"
    )
    try:
        cp = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
            capture_output=True, text=True, timeout=20,
        )
        if cp.returncode != 0:
            return False, (cp.stderr or cp.stdout or 'Failed to schedule wake task').strip()
        return True, (cp.stdout or iso).strip()
    except Exception as exc:
        return False, str(exc)
