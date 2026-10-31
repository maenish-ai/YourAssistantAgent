"""Release UI tests own independent Tcl interpreters; finalize them on their thread."""
import gc
import threading
import pytest


@pytest.fixture(autouse=True)
def collect_ui_cycles_on_test_thread():
    # A later HTTP/browser worker must not become the GC thread that disposes a
    # destroyed Tcl interpreter from an earlier UI test (Tcl aborts on that).
    if threading.current_thread() is threading.main_thread():gc.collect()
    yield
    if threading.current_thread() is threading.main_thread():gc.collect()
