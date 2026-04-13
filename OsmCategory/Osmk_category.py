# -*- coding: utf-8 -*-
import asyncio
import json
from typing import Any, Dict, List
import libconf
import pytest
from MainConnectFunc import snmp_set, snmp_get, get_full_ssh_output, snmp_multiset, multi_snmp_get
from pysnmp.hlapi.asyncio import OctetString, Integer
import re
from unit_tests.SnmpV7alarm import klm_numbersE1, klm_numbersETH, klm_numbersEth100M
import paramiko
import time

# ----------------------------
# Пути к твоим JSON
# ----------------------------
PATH_EQ = r"C:\Users\mikhailov_gs.SUPERTEL\PycharmProjects\STwebTestingNew\OIDstatusNEW.json"
PATH_OIDS = r"C:\Users\mikhailov_gs.SUPERTEL\PycharmProjects\STwebTestingNew\OsmCategory\OsmCategory.json"

# ----------------------------
# Загрузка конфигов
# ----------------------------

with open(PATH_EQ, "r", encoding="utf-8") as f:
    EQ_ALL = json.load(f)

with open(PATH_OIDS, "r", encoding="utf-8") as f:
    OID_DB = json.load(f)
EQ = EQ_ALL["CurrentEQ"]
EQ_NAME = EQ["name"]
SLOTS_DICT: Dict[int, str] = {int(k): v for k, v in EQ["slots_dict"].items()}
EQ_CURRENT = EQ_ALL[EQ_NAME]
CATEGORY_BLOCKS_DB = OID_DB["Category"][EQ_NAME]["block"]
LABEL_BLOCKS_DB = OID_DB["Label"][EQ_NAME]
MASK_BLOCKS_DB = OID_DB["Mask"][EQ_NAME]
LOOP_BLOCKS_DB = OID_DB["Loop"][EQ_NAME]
TRACE_BLOCKS_DB = OID_DB["Trace"][EQ_NAME]
EQUIPMENT_DATA = OID_DB["Category"][EQ_NAME].get("equipment", {})
SYNC_DATA = OID_DB["Category"][EQ_NAME].get("sync", {})


# ----------------------------
# Вспомогательные функции
# ----------------------------
def device_reboot():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(EQ["ipaddr"], port=22, username='admin', password=EQ["pass"])
    shell = ssh.invoke_shell()
    shell.send('reload\n')
    time.sleep(1)
    shell.send('y\n')
    ssh.close()
    time.sleep(150)


def installed_blocks(slots_dict: Dict[int, str]) -> List[str]:
    return sorted({b for b in slots_dict.values() if b and b != "Free"})


INSTALLED_BLOCKS = [
    b for b in installed_blocks(SLOTS_DICT)
    if b in CATEGORY_BLOCKS_DB
]


def build_full_oid(block, base_oid: str, slot: int, depth: int):
    if not base_oid.endswith('.'):
        base_oid += '.'

    if depth <= 0:
        return [base_oid]
    if depth == 1:
        return [f"{base_oid}{slot}"]

    if any(name in block for name in
           ["STM", "Eth1000", "Eth10/100", "Eth100M", "21E1", "63E1", "63E1M", "Eth1000M", "KC"]):
        if depth == 2:
            return [f"{base_oid}{slot}.{port}"
                    for port in range(1, EQ_CURRENT["blockOID"]["quantPort"][block] + 1)]
        if depth >= 3:
            if "STM" in block or "Eth1000" in block:
                return [f"{base_oid}{slot}.{port}.{vc}"
                        for port in range(1, EQ_CURRENT["blockOID"]["quantPort"][block] + 1)
                        for vc in range(1, EQ_CURRENT["blockOID"]["quantCnctPort"][block] + 1)]
            if "Eth10/100" in block:
                return [f"{base_oid}{slot}.{port}.{1}.{klm_numbersETH(vc)}"
                        for port in range(1, EQ_CURRENT["blockOID"]["quantPort"][block] + 1)
                        for vc in range(1, EQ_CURRENT["blockOID"]["quantCnctPort"][block] + 1)]
            if "Eth100M" in block:
                return [f"{base_oid}{slot}.{port}.{1}.{klm_numbersEth100M(vc)}"
                        for port in range(1, EQ_CURRENT["blockOID"]["quantPort"][block] + 1)
                        for vc in range(1, EQ_CURRENT["blockOID"]["quantCnctPort"][block] + 1)]
            elif "E1" in block:
                return [f"{base_oid}{slot}.{port}.{1}.{klm_numbersE1(vc)}"
                        for port in range(1, EQ_CURRENT["blockOID"]["quantPort"][block] + 1)
                        for vc in range(1, EQ_CURRENT["blockOID"]["quantCnctPort"][block] + 1)]


def bytes_from_snmp_value(val) -> bytes:
    if isinstance(val, bytes):
        return val
    if isinstance(val, str):
        return val.encode(errors="ignore")
    return str(val).encode(errors="ignore")


# ----------------------------
# Category: read configfile equipment
# ----------------------------

async def config_category_equipment():
    var = get_full_ssh_output("zcat /var/volatile/tmp/osmkm/config/category.cfg.gz")
    conf = libconf.loads(var)
    invalid_category = []

    def find_category(data):
        if isinstance(data, (dict, libconf.AttrDict)):
            for key, value in data.items():
                if any(c.isdigit() and c != '4' for c in str(value)):
                    invalid_category.append([f"{key} - {value}"])
                find_category(value)
        elif isinstance(data, list):
            for item in data:
                find_category(item)

    find_category(conf)
    if invalid_category:
        return invalid_category
    else:
        return True


async def config_block_equipment(slot):
    if len(str(slot)) < 2:
        slot = f"0{slot}"
    var = get_full_ssh_output(f"zcat /var/volatile/tmp/osmkm/config/PM{slot}.INI.cfg.gz")
    conf = libconf.loads(var)

    invalid_category = []

    def find_category(data):
        if isinstance(data, (dict, libconf.AttrDict)):
            for key, value in data.items():
                if "Category" in str(key):
                    if any(c.isdigit() and c != '4' for c in str(value)):
                        invalid_category.append([f"{key} - {value}"])
                find_category(value)
        elif isinstance(data, list):
            for item in data:
                find_category(item)

    find_category(conf)
    if invalid_category:
        return invalid_category
    else:
        return True


async def config_category_sync():
    var = get_full_ssh_output("zcat /var/volatile/tmp/osmkm/config/sync.cfg.gz")
    conf = libconf.loads(var)
    invalid_category = []

    def find_category(data):
        if isinstance(data, (dict, libconf.AttrDict)):
            for key, value in data.items():
                if "Category" in str(key):
                    if any(c.isdigit() and c != '4' for c in str(value)):
                        invalid_category.append([f"{key} - {value}"])
                find_category(value)
        elif isinstance(data, list):
            for item in data:
                find_category(item)

    find_category(conf)
    return invalid_category if invalid_category else True


async def config_label(slot, block):
    slot_str = f"{slot:0>2}"
    var = get_full_ssh_output(f"zcat /var/volatile/tmp/osmkm/config/PM{slot_str}.INI.cfg.gz")
    conf = libconf.loads(var)
    target_label = f"{block}-{slot}"
    invalid_labels = []

    def find_labels(data):
        if isinstance(data, (dict, libconf.AttrDict)):
            for key, value in data.items():
                if "Label" in str(key):
                    if value[0] != target_label:
                        invalid_labels.append({key: value})
                find_labels(value)
        elif isinstance(data, list):
            for item in data:
                find_labels(item)

    find_labels(conf)
    return invalid_labels if invalid_labels else True


async def config_mask(slot):
    slot_str = f"{slot:0>2}"
    output = get_full_ssh_output(f"zcat /var/volatile/tmp/osmkm/config/PM{slot_str}.INI.cfg.gz")
    conf = libconf.loads(output)
    con_values = []

    def check_masks(data, prefix=""):
        if isinstance(data, dict):
            for key, value in data.items():
                new_prefix = f"{prefix}_{key}" if prefix else key
                if "Mask" in key and isinstance(value, list):
                    if any(v != 0 for v in value):
                        con_values.append(f"{new_prefix} - {value}")
                else:
                    check_masks(value, new_prefix)
        elif isinstance(data, list):
            for item in data:
                check_masks(item, prefix)

    check_masks(conf)
    return con_values if con_values else True


async def config_loop(slot):
    slot_str = f"{slot:0>2}"
    var = get_full_ssh_output(f"zcat /var/volatile/tmp/osmkm/config/PM{slot_str}.INI.cfg.gz | grep Loop")
    conf = libconf.loads(var)

    loop_data = conf.get("Loop", [])

    if all(val == 1 for val in loop_data):
        return True
    return [f"{slot} - Port{i}: {v}" for i, v in enumerate(loop_data, 1) if v != 1]


async def config_trace(slot, block):
    con_values = []
    slotNew = slot
    if len(str(slot)) < 2:
        slotNew = f"0{slot}"
    var = get_full_ssh_output(f"zcat /var/volatile/tmp/osmkm/config/PM{slotNew}.INI.cfg.gz | grep Trace")
    conf = libconf.loads(var)
    for i in conf:
        for z in conf[i]:
            if f"{block}-{slot}" not in z:
                con_values.append(i)
    if con_values:
        return list(set(con_values))
    else:
        return True


# ----------------------------
# Category: process/read blocks
# ----------------------------

async def process_category_block(slots_dict: Dict[int, str], block: str, block_data: Dict[str, list]):
    slots = [s for s, b in slots_dict.items() if b == block]
    for slot in slots:
        for obj, (oid, length, depth) in block_data.items():
            x = b"\x04" * int(length)
            full_oid = build_full_oid(block, str(oid), int(slot), int(depth))
            data_to_set = [[f, OctetString(x)] for f in full_oid]
            await snmp_multiset(data_to_set)


async def reading_category_block(slots_dict: Dict[int, str], block: str, block_data: Dict[str, list]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    slots = [s for s, b in slots_dict.items() if b == block]
    for slot in slots:
        for obj, (oid, length, depth) in block_data.items():
            full_oid = build_full_oid(block, str(oid), int(slot), int(depth))
            out[f"{obj}@slot{slot}"] = await multi_snmp_get(full_oid)
    return out


# ----------------------------
# Category: process/read equipment
# ----------------------------

async def process_category_equipment(equipment_data: Dict[str, list]):
    for obj, (oid, length, depth) in equipment_data.items():
        if int(depth) != 0:
            continue
        x = b"\x04" * int(length)
        await snmp_set(f"{oid}0", OctetString(x))


async def reading_category_equipment(equipment_data: Dict[str, list]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for obj, (oid, length, depth) in equipment_data.items():
        if int(depth) != 0:
            continue
        out[f"{obj}@equipment"] = await snmp_get(str(oid))
    return out


# ----------------------------
# Category: process/read sync
# ----------------------------

async def process_category_sync(sync_data: Dict[str, list], priornum):
    for obj, (oid, length, depth) in sync_data.items():
        x = b"\x04" * int(length)
        full_oid = f"{oid}{priornum}"

        await snmp_set(full_oid, OctetString(x))


async def reading_category_sync(equipment_data: Dict[str, list], priornum) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for obj, (oid, length, depth) in equipment_data.items():
        if int(depth) != 0:
            continue
        full_oid = f"{oid}{priornum}"
        out[f"{obj}@sync"] = await snmp_get(str(full_oid))
    return out


# ----------------------------
# Label / Mask / Loop / Trace
# ----------------------------

def label_payload(block: str, slot: int, limits: Dict[str, int]) -> str:
    x = f"{block}-{slot}"
    return x[: int(limits["max"])]


def trace_payload(block: str, slot: int) -> str:
    x = f"{block}-{slot}"
    return (x[:15]).ljust(15)


def trace_is_settable(obj_name: str) -> bool:
    return ("TraceTD" in obj_name) or ("expected" in obj_name)


async def process_label_block(slots_dict: Dict[int, str], block: str, block_data: Dict[str, list]):
    slots = [s for s, b in slots_dict.items() if b == block]
    for slot in slots:
        for obj, (oid, depth, limits) in block_data.items():
            x = label_payload(block, int(slot), limits)
            full_oid = build_full_oid(block, str(oid), int(slot), int(depth))
            data_to_set = [[f, OctetString(x)] for f in full_oid]
            await snmp_multiset(data_to_set)


async def reading_label_block(slots_dict: Dict[int, str], block: str, block_data: Dict[str, list]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    slots = [s for s, b in slots_dict.items() if b == block]
    for slot in slots:
        for obj, (oid, depth, limits) in block_data.items():
            full_oid = build_full_oid(block, str(oid), int(slot), int(depth))
            out[f"{obj}@slot{slot}"] = await multi_snmp_get(full_oid)
    return out


async def process_mask_block(slots_dict: Dict[int, str], block: str, block_data: Dict[str, list]):
    slots = [s for s, b in slots_dict.items() if b == block]
    for slot in slots:
        for obj, (oid, _max_value, depth) in block_data.items():
            full_oid = build_full_oid(block, str(oid), int(slot), int(depth))
            data_to_set = [[f, Integer(1)] for f in full_oid]
            await snmp_multiset(data_to_set)


async def reading_mask_block(slots_dict: Dict[int, str], block: str, block_data: Dict[str, list]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    slots = [s for s, b in slots_dict.items() if b == block]
    for slot in slots:
        for obj, (oid, _max_value, depth) in block_data.items():
            full_oid = build_full_oid(block, str(oid), int(slot), int(depth))
            out[f"{obj}@slot{slot}"] = await multi_snmp_get(full_oid)

    return out


async def process_loop_block(slots_dict: Dict[int, str], block: str, block_data: Dict[str, list], value: int):
    slots = [s for s, b in slots_dict.items() if b == block]
    for slot in slots:
        for obj, (oid, depth) in block_data.items():
            full_oid = build_full_oid(block, str(oid), int(slot), int(depth))
            data_to_set = [[f, Integer(value)] for f in full_oid]
            await snmp_multiset(data_to_set)


async def reading_loop_block(slots_dict: Dict[int, str], block: str, block_data: Dict[str, list]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    slots = [s for s, b in slots_dict.items() if b == block]
    for slot in slots:
        for obj, (oid, depth) in block_data.items():
            full_oid = build_full_oid(block, str(oid), int(slot), int(depth))
            out[f"{obj}@slot{slot}"] = await multi_snmp_get(full_oid)
    return out


async def process_trace_block(slots_dict: Dict[int, str], block: str, block_data: Dict[str, list]):
    slots = [s for s, b in slots_dict.items() if b == block]
    for slot in slots:
        x = trace_payload(block, int(slot))
        for obj, (oid, depth, _null) in block_data.items():
            if not trace_is_settable(obj):
                continue
            full_oid = build_full_oid(block, str(oid), int(slot), int(depth))
            data_to_set = [[f, OctetString(x)] for f in full_oid]
            await snmp_multiset(data_to_set)


async def reading_trace_block(slots_dict: Dict[int, str], block: str, block_data: Dict[str, list]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    slots = [s for s, b in slots_dict.items() if b == block]
    for slot in slots:
        for obj, (oid, depth, _null) in block_data.items():
            if not trace_is_settable(obj):
                continue
            full_oid = build_full_oid(block, str(oid), int(slot), int(depth))
            out[f"{obj}@slot{slot}"] = await multi_snmp_get(full_oid)
    return out
