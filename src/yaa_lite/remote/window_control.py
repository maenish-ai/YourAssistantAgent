"""Observed Windows window/tab operations; graceful close, never process killing."""
from pathlib import PureWindowsPath
import os
import secrets
import time


class WindowControl:
    @staticmethod
    def _process_image(pid):
        import ctypes as c
        from ctypes import wintypes as w
        kernel=c.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
        kernel.QueryFullProcessImageNameW.argtypes=[w.HANDLE,w.DWORD,w.LPWSTR,c.POINTER(w.DWORD)]
        kernel.CloseHandle.argtypes=[w.HANDLE]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:return ''
        try:
            size=w.DWORD(32768);buffer=c.create_unicode_buffer(size.value)
            return PureWindowsPath(buffer.value).name.lower() if kernel.QueryFullProcessImageNameW(handle,0,buffer,c.byref(size)) else ''
        finally:kernel.CloseHandle(handle)

    def _uia_ready(self):
        if not getattr(self._uia_thread,'initialized',False):
            import comtypes
            comtypes.CoInitializeEx(0);self._uia_thread.initialized=True

    def _enumerate_windows(self):
        from pywinauto import Desktop
        return Desktop(backend='win32').windows(visible_only=True)

    def list_windows(self):
        with self._lock,self._session() as user:
            rows=[];observed={};deadline=time.monotonic()+5
            for window in self._enumerate_windows():
                if len(rows)>=80 or time.monotonic()>deadline:break
                try:
                    title=window.window_text();pid=window.process_id()
                    if not title or pid==os.getpid() or not window.is_visible():continue
                    if title in {'Program Manager','Windows Input Experience'}:continue
                    identifier=secrets.token_urlsafe(10);image=self._process_image(pid)
                    observed[identifier]=(window,pid,time.monotonic(),image)
                    rows.append({'id':identifier,'title':title[:220],'process':image,'active':window.handle==user.GetForegroundWindow()})
                except Exception:continue
            self._windows=observed
            return {'windows':rows,'note':'Observed open windows. IDs expire after 90 seconds; close requests can show unsaved-work dialogs.'}

    def _window_entry(self,identifier):
        from .desktop import DesktopError
        item=self._windows.get(str(identifier))
        if not item or time.monotonic()-item[2]>90:raise DesktopError('حدّث قائمة النوافذ قبل التحكم بها.')
        window,pid,_,_=item
        if not window.is_visible() or window.process_id()!=pid:raise DesktopError('تغيّرت النافذة. حدّث قائمة النوافذ.')
        return item

    def _focus_window(self,window,user):
        from .desktop import DesktopError
        if window.is_minimized():window.restore()
        window.set_focus()
        if user.GetForegroundWindow()!=window.handle:raise DesktopError('لم تنتقل النافذة إلى المقدمة؛ لم أرسل كتابة أو اختصاراً لنافذة أخرى.')

    def window_action(self,identifier,action):
        from .desktop import DesktopError
        with self._lock,self._session() as user:
            window,_,_,_=self._window_entry(identifier)
            if action=='focus':self._focus_window(window,user)
            elif action in {'minimize','maximize','restore'}:getattr(window,action)()
            elif action=='close':
                import ctypes as c
                from ctypes import wintypes as w
                user.PostMessageW.argtypes=[w.HWND,w.UINT,c.c_size_t,c.c_ssize_t]
                if not user.PostMessageW(window.handle,0x0010,0,0):raise DesktopError('رفض Windows طلب إغلاق النافذة.')
            else:raise DesktopError('إجراء النافذة غير مدعوم.')
            return {'ok':True,'action':action,'title':window.window_text() if action!='close' else '',
                    'result':'أُرسل الإجراء. الإغلاق عادي؛ قد تظهر مطالبة بحفظ عمل غير محفوظ. لم أقتل العملية.'}

    def _browser_window(self,identifier,user):
        from .desktop import DesktopError
        if not identifier:
            listing=self.list_windows()
            identifier=next((row['id'] for row in listing['windows'] if row['active']),None)
        window,pid,_,image=self._window_entry(identifier)
        if image not in {'msedge.exe','chrome.exe','firefox.exe','brave.exe','vivaldi.exe','opera.exe'}:
            raise DesktopError('النافذة المحددة ليست متصفحاً مدعوماً. اعرض النوافذ واختر المتصفح أولاً.')
        return window,pid

    def list_browser_tabs(self,window_id=''):
        with self._lock,self._session() as user:
            window,pid=self._browser_window(window_id,user);self._focus_window(window,user);self._uia_ready()
            from pywinauto import Desktop
            root=Desktop(backend='uia').window(handle=window.handle).wrapper_object()
            rows=[];self._tabs={};deadline=time.monotonic()+5
            # Limit to browser chrome, excluding tab widgets buried in webpages.
            for tab in root.descendants(control_type='TabItem',depth=5):
                if len(rows)>=100 or time.monotonic()>deadline:break
                try:
                    if not tab.is_visible():continue
                    identifier=secrets.token_urlsafe(10)
                    self._tabs[identifier]=(tab,window,pid,time.monotonic())
                    rows.append({'id':identifier,'title':tab.window_text()[:220]})
                except Exception:continue
            return {'tabs':rows,'window':window.window_text(),'note':'Current tabs only, not a record of tabs opened by earlier tasks. Never infer ownership/history.'}

    def tab_action(self,identifier,action):
        from .desktop import DesktopError
        if action not in {'focus','close'}:raise DesktopError('إجراء التبويب غير مدعوم.')
        with self._lock,self._session() as user:
            item=self._tabs.get(str(identifier))
            if not item or time.monotonic()-item[3]>60:raise DesktopError('حدّث قائمة التبويبات قبل اختيار تبويب.')
            tab,window,pid,_=item
            if window.process_id()!=pid or not tab.is_visible():raise DesktopError('تغيّر التبويب. حدّث قائمته.')
            self._focus_window(window,user)
            tab.select()
            if not tab.is_selected():raise DesktopError('تعذر تحديد التبويب؛ لم أرسل طلب إغلاق.')
            if action=='close':
                self.input({'action':'keys','keys':['CTRL','W']});self._tabs.pop(str(identifier),None)
            return {'ok':True,'action':action,'result':'تم اختيار التبويب وإرسال الإجراء؛ راقب الشاشة لأي مطالبة بحفظ البيانات.'}

    def browser_action(self,action,window_id=''):
        from .desktop import DesktopError
        shortcuts={'close_tab':['CTRL','W'],'new_tab':['CTRL','T'],'back':['ALT','LEFT'],
                   'forward':['ALT','RIGHT'],'refresh':['CTRL','R'],'reopen_tab':['CTRL','SHIFT','T']}
        if action not in shortcuts:raise DesktopError('إجراء المتصفح غير مدعوم.')
        with self._lock,self._session() as user:
            window,_=self._browser_window(window_id,user);self._focus_window(window,user)
            return self.input({'action':'keys','keys':shortcuts[action]})
