"""
main.py — Entry point for the Urban Disaster Evacuation & Smart Traffic Router.

Run with:
    python main.py
    (or: ./venv/Scripts/python.exe main.py on Windows with the project venv)
"""

import sys
import os

# Ensure the evacuation_router package directory is on sys.path
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from ui import EvacuationApp


def handler(environ, start_response):
    """WSGI compatibility handler for Vercel deployment."""
    start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
    index_path = os.path.join(_HERE, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "rb") as f:
            return [f.read()]
    return [b"Evacuation Router Online"]


def main() -> None:
    """Instantiate and launch the desktop EvacuationApp dashboard."""
    app_instance = EvacuationApp()
    app_instance.run()


app = handler


if __name__ == "__main__":
    main()


