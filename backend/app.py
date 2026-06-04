"""
Single entry point for the whole backend.

Run:  python app.py

This starts two things at once:
  - the Flask API (profiles, runs, settings) on http://127.0.0.1:6500
  - the file Monitor, watching every active profile's inbound folder
The Monitor runs in a background thread so the API can run in the main one.
"""

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from logging_setup import get_logger
from api.profiles import app
from Monitor_agent.watchdog import get_active_inbound_paths, start_monitoring

log = get_logger("App")


def start_monitor_in_background():
    """
    Start the file Monitor in a daemon thread.
    Parameters: none.
    Returns: None.
    """
    paths = get_active_inbound_paths()
    log.info("Starting Monitor for %d folder(s)", len(paths))
    thread = threading.Thread(target=start_monitoring, args=(paths,), daemon=True)
    thread.start()


def serve_api():
    """
    Serve the Flask API. Use the production server (waitress) if it is
    installed, otherwise fall back to Flask's built-in server.
    Parameters: none.
    Returns: None (blocks forever).
    """
    try:
        from waitress import serve
        log.info("Starting API (waitress) on http://127.0.0.1:6500")
        serve(app, host="127.0.0.1", port=6500, threads=8)
    except ImportError:
        log.warning("waitress not installed — using Flask's built-in server. "
                    "Run 'pip install waitress' for the production server.")
        app.run(host="127.0.0.1", port=6500, debug=False, threaded=True)


if __name__ == "__main__":
    start_monitor_in_background()
    serve_api()
