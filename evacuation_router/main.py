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


def main() -> None:
    """
    Application entry point.

    Instantiates and launches the EvacuationApp dashboard.
    All graph loading, window creation, and event loops are
    managed by the EvacuationApp class in ui.py.
    """
    app = EvacuationApp()
    app.run()


if __name__ == "__main__":
    main()
