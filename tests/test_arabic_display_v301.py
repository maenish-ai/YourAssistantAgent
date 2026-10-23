"""Regression tests: display must preserve the original logical Unicode."""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'src/yaa_lite/text_first_v300.py'

def visual_arabic():
    tree = ast.parse(SRC.read_text(encoding='utf-8'))
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_visual_arabic')
    module = ast.Module(body=[func], type_ignores=[])
    scope = {}
    exec(compile(module, str(SRC), 'exec'), scope)
    return scope['_visual_arabic']

def test_arabic_round_trip():
    f = visual_arabic()
    for value in [
        'أهلًا، كيف أقدر أساعدك اليوم؟',
        'هذا هو الرد العربي الصحيح بعد التصحيح.\nهنا سطر آخر.',
        'بدي أنشر على فيسبوك الساعة 7 مش الساعة 8',
        'فتح GitHub — رابط https://github.com/maenish-ai/YourAssistantAgent',
        'مرحبا 👋 كيف الحال؟ 😊',
        'سوف أقرأ الملف (Readme.md) أولًا.',
        '123 - أحمد - ABC - 456',
    ]:
        assert f(value) == value

def test_does_not_insert_visual_presentation_forms():
    f = visual_arabic()
    response = 'أهلا وسهلا بكم في برنامجنا'
    rendered = f(response)
    assert all(not (0xFB50 <= ord(c) <= 0xFEFF) for c in rendered)
    assert rendered == response

def test_no_pre_shaping_or_bidi_on_wrapping_text():
    source = SRC.read_text(encoding='utf-8')
    assert 'arabic_reshaper' not in source.split('def _visual_arabic', 1)[1].split('def _btn', 1)[0].replace('arabic_reshaper + python-bidi', '')
    assert 'get_display(' not in source
    assert "justify='right'" in source
