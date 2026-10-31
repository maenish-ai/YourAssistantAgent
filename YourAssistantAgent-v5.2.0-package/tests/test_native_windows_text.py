import os
import pytest

pytestmark=pytest.mark.skipif(os.name!='nt',reason='Windows RichEdit integration')


def test_windows_editor_arabic_typing_emoji_and_send_preserve_logical_text():
    import tkinter as tk
    from yaa_lite.ui.native_text import WindowsText,utf16_length
    root=tk.Tk();root.geometry('600x300')
    editor=WindowsText(root,height=3,rtl=True);editor.pack(fill='both',expand=True);root.update()
    try:
        text='أهلاً بك في Facebook 123 😀\nرابط https://example.test'
        editor.insert('end',text)
        assert editor.get('1.0','end-1c')==text
        assert editor._range().start==utf16_length(text)
        editor.delete('1.0','end')
        for char in 'فوت على الفيسبوك':editor._send(0x0102,ord(char),0)
        assert editor.get()=='فوت على الفيسبوك'
        calls=[];editor.bind('<Return>',lambda event:calls.append('send') or 'break')
        editor._send(0x0100,13,0);editor._send(0x0102,13,0);editor._send(0x0101,13,0)
        assert calls==['send'] and editor.get()=='فوت على الفيسبوك'
        editor.configure(state='disabled');editor._send(0x0102,ord('x'),0)
        assert editor.get()=='فوت على الفيسبوك'
    finally:root.destroy()
