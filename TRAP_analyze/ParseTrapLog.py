import json
import time
import re
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
TRAP_DIR = BASE_DIR
TEXT_LOG = TRAP_DIR / "received_traps.log"
JSONL_LOG = TRAP_DIR / "received_traps.jsonl"

import json


def parse_snmp_log(target_oid, target_value):
    with open(JSONL_LOG, "r", encoding="utf-8") as f:
        content = f.read()

    decoder = json.JSONDecoder()
    pos = 0
    content = content.strip()

    while pos < len(content):
        try:
            trap_data, next_pos = decoder.raw_decode(content, pos)
            pos = next_pos

            while pos < len(content) and content[pos].isspace():
                pos += 1

            var_binds = trap_data.get("var_binds", [])

            for bind in var_binds:
                print(bind, target_oid, target_value)
                if bind.get("oid") == target_oid and str(bind.get("value")) == str(target_value):
                    return (bind.get("oid"), str(bind.get("value")))
        except json.JSONDecodeError as e:
            print(f"Ошибка в структуре файла на позиции {e.pos}")
            break
    return False


def clear_trap_log():
    TRAP_DIR.mkdir(parents=True, exist_ok=True)
    for p in (TEXT_LOG, JSONL_LOG):
        try:
            with p.open("w", encoding="utf-8") as f:
                f.truncate(0)
        except Exception:
            pass


def wait_trap(oid: str, code: int, timeout_s: float = 3.0, poll_s: float = 0.5):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        last = parse_snmp_log(oid, code)
        if last != False:
            return last
        time.sleep(poll_s)
    return last
