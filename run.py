"""Entry point: python run.py check / doctor / smoke / run / compare / summarize."""

import sys
import multiprocessing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jev_vllm.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"Run failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
