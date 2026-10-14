from datetime import datetime, timedelta

from your_assistant_agent.smart_agent import SmartPlanner
from your_assistant_agent.wake_support import build_magic_packet, normalize_mac


def test_arabic_partial_name_keyword():
    p = SmartPlanner('ar').parse(
        'اليوم على الساعة 8 مساء شارك آخر منشور على جميع المجموعات التي جزء من اسمها يكون صويلح',
        'https://www.facebook.com/example',
    )
    assert p.group_keyword == 'صويلح'
    assert p.run_time == '20:00'
    assert p.run_once_at


def test_magic_packet_shape():
    assert normalize_mac('AA:BB:CC:DD:EE:FF') == 'AABBCCDDEEFF'
    packet = build_magic_packet('AA:BB:CC:DD:EE:FF')
    assert len(packet) == 102
    assert packet[:6] == b'\xff' * 6
