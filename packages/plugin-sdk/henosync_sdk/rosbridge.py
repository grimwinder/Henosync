"""
Henosync Plugin SDK — Rosbridge utilities
==========================================
Shared Twisted reactor lifecycle for rosbridge-based device plugins.

The Twisted reactor is a process-wide singleton — once started it cannot
be restarted. If two plugin modules each try to call reactor.run() they
race and the second one crashes.

Usage in your plugin:

    from henosync_sdk.rosbridge import ensure_reactor

    # In connect():
    reactor_ready = ensure_reactor()
    await asyncio.get_event_loop().run_in_executor(
        None, lambda: reactor_ready.wait(5.0)
    )
    if not reactor_ready.is_set():
        return False, "Twisted reactor failed to start"

    from twisted.internet import reactor as _reactor
    _reactor.callFromThread(ros.connect)
"""

import threading

_reactor_started = threading.Event()
_reactor_ready = threading.Event()


def ensure_reactor() -> threading.Event:
    """
    Start the Twisted reactor on a dedicated background thread if not already running.

    Returns the reactor_ready Event — wait on it before calling callFromThread.
    Safe to call from multiple plugin modules; only one reactor thread is ever started.
    """
    if not _reactor_started.is_set():
        _reactor_started.set()

        def _run() -> None:
            from twisted.internet import reactor
            reactor.callWhenRunning(_reactor_ready.set)
            reactor.run(installSignalHandlers=False)

        threading.Thread(target=_run, name="twisted-reactor", daemon=True).start()

    return _reactor_ready
