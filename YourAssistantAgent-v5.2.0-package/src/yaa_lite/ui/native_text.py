"""Native Windows RichEdit for logical Unicode, shaping, bidi and caret editing.

Tk 8.6 Text on Windows does not implement a full Unicode bidi editor. Alignment
or pre-reversing strings cannot repair its caret behavior. RichEdit is part of
Windows; this adapter keeps the small Text API used by the chat shell.
"""
from __future__ import annotations
import os
import tkinter as tk
import unicodedata
from types import SimpleNamespace


def utf16_length(text):return len(text.encode('utf-16-le'))//2


def rtl_paragraph(text,default=False):
    for char in text:
        direction=unicodedata.bidirectional(char)
        if direction in ('R','AL'):return True
        if direction=='L':return False
    return default


class WindowsText(tk.Frame):
    def __init__(self,master,**options):
        import ctypes as c
        from ctypes import wintypes as w
        self.c,self.w=c,w;self._callbacks={};self._tags={};self._scroll_callback=None
        self._default_rtl=bool(options.pop('rtl',False));self._readonly=options.get('state')=='disabled'
        self._foreground=options.get('fg','#eef2ff');self._font=options.get('font',('Segoe UI',12))
        self._suppress_return=False;self._hwnd=0
        super().__init__(master,bg=options.get('bg','#ffffff'),height=int(options.get('height',12))*24+20,width=420)
        self.user=c.WinDLL('user32',use_last_error=True);self.library=c.WinDLL('Msftedit.dll',winmode=0x800)
        self.user.CreateWindowExW.argtypes=[w.DWORD,w.LPCWSTR,w.LPCWSTR,w.DWORD,c.c_int,c.c_int,c.c_int,c.c_int,w.HWND,w.HMENU,w.HINSTANCE,c.c_void_p]
        self.user.CreateWindowExW.restype=w.HWND
        self.user.SendMessageW.argtypes=[w.HWND,w.UINT,c.c_size_t,c.c_ssize_t];self.user.SendMessageW.restype=c.c_ssize_t
        self.user.MoveWindow.argtypes=[w.HWND,c.c_int,c.c_int,c.c_int,c.c_int,w.BOOL]
        self.user.DestroyWindow.argtypes=[w.HWND];self.user.IsWindow.argtypes=[w.HWND];self.user.SetFocus.argtypes=[w.HWND]
        self.user.GetKeyState.argtypes=[c.c_int];self.user.GetKeyState.restype=c.c_short
        # No WS_EX_LAYOUTRTL: mirroring the whole surface would reverse bidi a
        # second time. Direction belongs to each logical paragraph.
        style=0x40000000|0x10000000|0x00010000|0x0004|0x0040|0x0100|0x1000
        self._hwnd=self.user.CreateWindowExW(0,'RICHEDIT50W','',style,0,0,420,80,self.winfo_id(),None,self.library._handle,None)
        if not self._hwnd:super().destroy();raise OSError(c.get_last_error(),'Could not create Windows Unicode editor')
        self._send(0x0435,0,16*1024*1024)  # EM_EXLIMITTEXT
        self._send(0x0443,0,self._color(options.get('bg','#ffffff')))
        self._format(self._font,self._foreground)
        self._paragraph('',self._default_rtl)
        self._send(0x00cf,1 if self._readonly else 0,0)
        callback_type=c.WINFUNCTYPE(c.c_ssize_t,w.HWND,w.UINT,c.c_size_t,c.c_ssize_t)
        self._procedure=callback_type(self._window_proc)
        setter=getattr(self.user,'SetWindowLongPtrW',self.user.SetWindowLongW)
        setter.argtypes=[w.HWND,c.c_int,c.c_void_p];setter.restype=c.c_void_p
        self.user.CallWindowProcW.argtypes=[c.c_void_p,w.HWND,w.UINT,c.c_size_t,c.c_ssize_t];self.user.CallWindowProcW.restype=c.c_ssize_t
        self._original=setter(self._hwnd,-4,c.cast(self._procedure,c.c_void_p))
        if not self._original:raise OSError(c.get_last_error(),'Could not connect Windows editor events')
        super().bind('<Configure>',self._resize)
        super().bind('<Destroy>',self._destroy_native)

    def _send(self,message,first=0,second=0):
        return self.user.SendMessageW(self._hwnd,message,first,second)

    def _pointer(self,value):return self.c.cast(self.c.byref(value),self.c.c_void_p).value
    def _color(self,value):
        red,green,blue=self.winfo_rgb(value);return (red//256)|((green//256)<<8)|((blue//256)<<16)

    def _range(self,start=None,end=None):
        class Range(self.c.Structure):_fields_=[('start',self.w.LONG),('end',self.w.LONG)]
        value=Range()
        if start is None:self._send(0x0434,0,self._pointer(value))
        else:value=Range(start,start if end is None else end);self._send(0x0437,0,self._pointer(value))
        return value

    def _format(self,font=None,color=None):
        c,w=self.c,self.w
        class Format(c.Structure):
            _fields_=[('size',w.UINT),('mask',w.DWORD),('effects',w.DWORD),('height',w.LONG),('offset',w.LONG),('color',w.DWORD),('charset',w.BYTE),('pitch',w.BYTE),('face',w.WCHAR*32)]
        value=Format();value.size=c.sizeof(value);value.mask=0xe0000001
        font=font or self._font;value.face=str(font[0])[:31];value.height=int(font[1])*20
        value.effects=1 if 'bold' in font else 0;value.color=self._color(color or self._foreground)
        self._send(0x0444,1,self._pointer(value))

    def _paragraph(self,text,default=False,align=None):
        c,w=self.c,self.w
        class Para(c.Structure):
            _fields_=[('size',w.UINT),('mask',w.DWORD),('numbering',w.WORD),('effects',w.WORD),('start',w.LONG),('right',w.LONG),('offset',w.LONG),('alignment',w.WORD),('tabs_count',c.c_short),('tabs',w.LONG*32),('before',w.LONG),('after',w.LONG),('line',w.LONG),('style',c.c_short),('rule',w.BYTE),('outline',w.BYTE),('shading_weight',w.WORD),('shading_style',w.WORD),('num_start',w.WORD),('num_style',w.WORD),('num_tab',w.WORD),('border_space',w.WORD),('border_width',w.WORD),('borders',w.WORD)]
        rtl=rtl_paragraph(text,default);value=Para();value.size=c.sizeof(value);value.mask=0x10008
        value.effects=1 if rtl else 0;value.alignment=3 if align=='center' else (2 if rtl or align=='right' else 1)
        current=Para();current.size=c.sizeof(current);self._send(0x043d,0,self._pointer(current))
        if current.mask&0x10008==0x10008 and current.effects&1==value.effects and current.alignment==value.alignment:return
        self._send(0x0447,0,self._pointer(value))

    def _resize(self,event):
        if not self._hwnd:return
        self.user.MoveWindow(self._hwnd,0,0,event.width,event.height,True)
        rect=self.w.RECT(12,8,max(13,event.width-12),max(9,event.height-8));self._send(0x00b3,0,self._pointer(rect));self._notify_scroll()

    def _window_proc(self,handle,message,first,second):
        processed=False;result=0
        try:
            if message==0x0100 and first==13:
                shift=bool(self.user.GetKeyState(16)&0x8000)
                callback=self._callbacks.get('<Shift-Return>' if shift else '<Return>')
                if callback and callback(SimpleNamespace(state=1 if shift else 0))=='break':
                    self._suppress_return=True;return 0
            if message==0x0102 and first==13 and self._suppress_return:return 0
            if message==0x0101 and first==13:self._suppress_return=False
            if message==0x007b and '<Button-3>' in self._callbacks:
                point=self.w.POINT();self.user.GetCursorPos(self.c.byref(point))
                self._callbacks['<Button-3>'](SimpleNamespace(x_root=point.x,y_root=point.y));return 0
            # Paste Unicode text rather than executing/embedding clipboard RTF
            # objects in a command composer.
            result=self.user.CallWindowProcW(self._original,handle,0x0440 if message==0x0302 else message,13 if message==0x0302 else first,0 if message==0x0302 else second)
            processed=True
            if message in (0x0102,0x0302) and not self._readonly:
                selection=self._range();text=self.get('1.0','end-1c')
                prefix=text.encode('utf-16-le')[:selection.start*2].decode('utf-16-le',errors='ignore')
                self._paragraph(prefix.rsplit('\n',1)[-1],self._default_rtl)
            if message in (0x0102,0x020a,0x0115):self._notify_scroll()
            return result
        except Exception:
            return result if processed else self.user.CallWindowProcW(self._original,handle,message,first,second)

    def get(self,start='1.0',end='end-1c'):
        length=self._send(0x000e);buffer=self.c.create_unicode_buffer(length+1)
        self._send(0x000d,length+1,self.c.cast(buffer,self.c.c_void_p).value)
        # RichEdit has no Tk sentinel newline. Never strip a real final letter.
        return buffer.value.replace('\r\n','\n').replace('\r','\n')

    def insert(self,index,text,tag=None):
        text=str(text).replace('\r\n','\n').replace('\r','\n');position=utf16_length(self.get()) if index=='end' else (0 if index=='1.0' else self._range().start)
        self._range(position)
        style=self._tags.get(tag,{}) if isinstance(tag,str) else {}
        self._format(style.get('font'),style.get('foreground'))
        raw=text.replace('\n','\r');buffer=self.c.create_unicode_buffer(raw,utf16_length(raw)+1)
        self._send(0x00c2,1,self.c.cast(buffer,self.c.c_void_p).value)
        at=position
        for paragraph in text.split('\n'):
            self._range(at,at+utf16_length(paragraph))
            self._paragraph(paragraph,self._default_rtl,style.get('justify') if tag not in ('msg_rtl','msg_ltr') else None)
            at+=utf16_length(paragraph)+1
        self._range(position+utf16_length(text));self._notify_scroll()

    def delete(self,start,end):
        self._range(0,-1);empty=self.c.create_unicode_buffer('');self._send(0x00c2,1,self.c.cast(empty,self.c.c_void_p).value);self._notify_scroll()

    def configure(self,cnf=None,**options):
        if cnf:options.update(cnf)
        if 'state' in options:self._readonly=options.pop('state')=='disabled';self._send(0x00cf,int(self._readonly),0)
        if 'yscrollcommand' in options:self._scroll_callback=options.pop('yscrollcommand')
        if 'bg' in options:self._send(0x0443,0,self._color(options['bg']))
        # Text-only geometry/font options do not belong to a Tk Frame.
        frame={k:v for k,v in options.items() if k in ('bg','background','width','height','cursor')}
        if frame:super().configure(**frame)
    config=configure
    def tag_configure(self,name,**style):self._tags[name]=style
    def bind(self,sequence=None,func=None,add=None):
        if sequence in ('<Return>','<Shift-Return>','<Button-3>'):self._callbacks[sequence]=func;return sequence
        return super().bind(sequence,func,add)
    def focus_set(self):
        super().focus_set()
        if self._hwnd:self.user.SetFocus(self._hwnd)
    def see(self,index):self._range(-1,-1);self._send(0x00b7);self._notify_scroll()
    def yview(self,*args):
        total=max(1,self._send(0x00ba));first=self._send(0x00ce)
        if args:
            amount=int(float(args[1])*total)-first if args[0]=='moveto' else int(args[1])*(8 if len(args)>2 and args[2]=='pages' else 1)
            self._send(0x00b6,0,amount);self._notify_scroll()
        return (first/total,min(1,(first+max(1,self.winfo_height()//24))/total))
    def _notify_scroll(self):
        if callable(self._scroll_callback):self._scroll_callback(*self.yview())
    def _destroy_native(self,event):
        if event.widget is self and self._hwnd:
            if self.user.IsWindow(self._hwnd):self.user.DestroyWindow(self._hwnd)
            self._hwnd=0


def text_widget(master,**options):
    if os.name=='nt':return WindowsText(master,**options)
    options.pop('rtl',None)
    return tk.Text(master,**options)
