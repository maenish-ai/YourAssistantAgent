"""One owner thread for synchronous Playwright across desktop/mobile requests."""
from concurrent.futures import Future
import queue
import threading


class BrowserSession:
    def __init__(self,factory):
        self.factory=factory;self.queue=queue.Queue(maxsize=16);self.closed=threading.Event()
        self._state_lock=threading.Lock()
        self.thread=threading.Thread(target=self._run,daemon=True,name='yaa-facebook-browser')
        self.thread.start()

    def _run(self):
        browser=None
        try:
            while True:
                item=self.queue.get()
                if item is None:break
                operation,name,args,kwargs,future=item
                if not future.set_running_or_notify_cancel():continue
                try:
                    if browser is None:browser=self.factory()
                    if operation=='supports':result=callable(getattr(browser,name,None))
                    elif operation=='get':result=getattr(browser,name,'')
                    else:result=getattr(browser,name)(*args,**kwargs)
                    future.set_result(result)
                except BaseException as exc:future.set_exception(exc)
        finally:
            while True:
                try:
                    item=self.queue.get_nowait()
                    if item is not None:item[-1].cancel()
                except queue.Empty:break
            if browser is not None:
                try:browser.stop()
                except Exception:pass

    def _call(self,operation,name,*args,**kwargs):
        future=Future()
        with self._state_lock:
            if self.closed.is_set():raise RuntimeError('جلسة المتصفح أُغلقت؛ اطلب فتح Facebook مجدداً.')
            try:self.queue.put_nowait((operation,name,args,kwargs,future))
            except queue.Full:raise RuntimeError('المتصفح مشغول. انتظر نتيجة المهمة الحالية.')
        # Every backend action has its own bounded Playwright timeout. Do not
        # abandon a live publishing call and silently execute another in parallel.
        return future.result()

    def supports(self,name):return self._call('supports',name)
    @property
    def browser_backend(self):return self._call('get','browser_backend')
    def __getattr__(self,name):
        if name.startswith('_'):raise AttributeError(name)
        return lambda *args,**kwargs:self._call('call',name,*args,**kwargs)
    def stop(self):
        with self._state_lock:
            self.closed.set()
            while True:
                try:
                    item=self.queue.get_nowait()
                    if item is not None:item[-1].cancel()
                except queue.Empty:break
            self.queue.put_nowait(None)
        if self.thread is not threading.current_thread():self.thread.join(timeout=.5)
