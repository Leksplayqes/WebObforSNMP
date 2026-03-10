from __future__ import annotations

import os
from pathlib import Path

# project_root/.../trap_listener_entrypoint.py -> project_root
BASE_DIR = Path(__file__).resolve().parents[1]

TRAP_DIR = BASE_DIR / "TRAP_analyze"
TRAP_LOG_PATH = TRAP_DIR / "received_traps.log"
TRAP_DESCR_PATH = TRAP_DIR / "TrapDescript.json"


os.makedirs(TRAP_DIR, exist_ok=True)
os.chdir(TRAP_DIR)

from TrapListner import run_snmp_trap_listener


def main() -> None:
    run_snmp_trap_listener()


if __name__ == "__main__":
    main()