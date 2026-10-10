"""Packaged desktop sidecar: loopback HTTP, app-data settings, pipe-owned lifetime.

PyInstaller bundles tools as a package and data/monitor beside it in _MEIPASS.
The existing server resolves those read-only assets using its module __file__.
Only the explicit --data-dir receives settings and persistent review journals.
"""
import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path

# Keep package module paths identical in source and frozen distributions. A direct
# `python tools/desktop_runtime.py` invocation needs the repository on sys.path;
# PyInstaller already installs its package importer and must not use this branch.
if not getattr(sys, 'frozen', False) and __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.env_config import load_agent_env
from tools.monitor_server import Simulation, make_server


def create_server(data_dir, port=0):
    """Bind without loading the source checkout's .env or writing bundle assets."""
    data_dir = Path(data_dir).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    load_agent_env(data_dir / '.env')
    simulation = Simulation(
        audit_path=data_dir / 'track-reviews.jsonl',
        decision_audit_path=data_dir / 'event-decisions.jsonl',
        dashboard_audit_path=data_dir / 'dashboard-decisions.jsonl',
    )
    return make_server(port, simulation=simulation)


def serve(data_dir, port=0):
    server = create_server(data_dir, port)
    stopped = threading.Event()
    failed = threading.Event()

    def request_stop(*_):
        stopped.set()

    def watch_stdin():
        try:
            stream = sys.stdin
            if stream is not None:
                while stream.read(1):
                    pass  # The pipe is a lifetime lease, not a command protocol.
        except (OSError, ValueError):
            pass
        finally:
            request_stop()

    def run_server():
        try:
            server.serve_forever(poll_interval=.1)
        except Exception:
            failed.set()
        finally:
            request_stop()

    previous_handlers = {}
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[signum] = signal.signal(signum, request_stop)
    worker = threading.Thread(target=run_server, name='desktop-http', daemon=True)
    try:
        worker.start()
        # This is the only stdout protocol message; bind/listen has succeeded.
        print(json.dumps({'event': 'ready', 'port': server.server_port}, separators=(',', ':')), flush=True)
        threading.Thread(target=watch_stdin, name='desktop-parent-pipe', daemon=True).start()
        stopped.wait()
    finally:
        # shutdown() runs outside the serve_forever thread, avoiding deadlock.
        if worker.is_alive():
            server.shutdown()
            worker.join(timeout=3)
        server.server_close()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    if failed.is_set():
        print('LOW SKY desktop backend stopped unexpectedly.', file=sys.stderr, flush=True)
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True,
                        help='Writable desktop app-data directory; settings are read from its .env only')
    parser.add_argument('--port', type=int, default=0, help='Loopback port; 0 selects an available port')
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error('--port must be between 0 and 65535')
    try:
        return serve(args.data_dir, args.port)
    except Exception:
        # Config/provider/storage exceptions can contain secrets or private paths.
        print('LOW SKY desktop backend could not start; check app-data settings and bundled assets.',
              file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    # This entrypoint is a dedicated child process, never an embedded server.
    # serve() has closed the HTTP service and successful journal writes were
    # already fsynced. Optional SDK libraries may register unbounded atexit
    # joins; bypass those after parent EOF so an abandoned provider task cannot
    # keep the desktop sidecar alive. Library callers still receive main()'s code.
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
