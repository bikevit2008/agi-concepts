"""Entry point for the AGI Consciousness PoC system."""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env from project root
load_dotenv(PROJECT_ROOT / ".env")


def main() -> None:
    from src.tui.app import ConsciousnessApp

    app = ConsciousnessApp()
    app.run()


if __name__ == "__main__":
    main()
