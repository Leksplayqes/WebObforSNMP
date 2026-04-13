import asyncio
import re
import time

from MainConnectFunc import *
import pytest
from pysnmp.hlapi.asyncio import *
from pysnmp.hlapi import *
import asyncio
from Vivavi.ViaviControl import VIAVI_get_command, VIAVI_set_command, VIAVI_secndStage
from unit_tests.SnmpV7alarm import delete_commutation, check_alarmPH, klm_numbers, check_alarm_cnct, \
    create_commutationVC4, create_commutationVC12, create_commutationE1, check_alarm_cnctE1
from MainConnectFunc import oids as get_oids
from MainConnectFunc import oidsSNMP as get_oids_snmp
from MainConnectFunc import oidsVIAVI as get_viavi_oids

OIDS_SNMP = get_oids_snmp()
OIDS = get_oids()
OIDS_VIAVI = get_viavi_oids()
SLOTS_DICT = OIDS_SNMP.get("slots_dict", {})

''' Тест коммутации СТМ-N по уровню vc-4.
    Каждая итерация ~ 20сек. Проверяется отсутствие аварий при наличии коммутации
    и формируется одна битовая ошибка, отслуживается ее наличие на приеме.'''


async def generate_params_vc4():
    params = []
    for w in OIDS_VIAVI["wiring"]:
        if "STM" not in w["dev_interface"]:
            continue
        slot, port = int(w["dev_slot"]), int(w["dev_port"])
        if str(slot) in OIDS_SNMP["active_slots"]:
            alarm = await check_alarmPH(slot, port)
            if str(alarm) in ["1", "2"]:
                continue
            slot_key = oidsSNMP()["slots_dict"][w["dev_slot"]]
            max_vc4 = OIDS["blockOID"]["quantCnctPort"][slot_key]
            for vc4 in range(1, max_vc4 + 1):
                params.append((w, vc4))
    return params


TEST_DATA_VC4 = asyncio.run(generate_params_vc4())
test_ids_vc4 = [f"Slot:{w['dev_slot']}-Port:{w['dev_port']}-VC4:{vc4}" for w, vc4 in TEST_DATA_VC4]


@pytest.mark.asyncio
@pytest.mark.parametrize("w, vc4", TEST_DATA_VC4, ids=test_ids_vc4)
async def test_commutationsVC4(w, vc4):
    slot, port = int(w["dev_slot"]), int(w["dev_port"])
    block, dev, p_dev = w["viavi_interface"], w["viavi_device"], w["viavi_port"]

    await delete_commutation()
    await create_commutationVC4(slot, port, vc4)

    VIAVI_secndStage(vc="vc-4", device_name=dev, port_name=p_dev)

    cmds = [
        f":SENSE:SDH:CHANNEL:STMN {vc4}",
        ":ABORt",
        ":SOURce:GEN:ERRor:TYPE BIT"
    ]
    VIAVI_set_command(block, ";".join(cmds), "", "vc-4", dev, p_dev)

    await asyncio.sleep(1)
    VIAVI_set_command(block, ":INITiate", " ", "vc-4", dev, p_dev)

    await asyncio.sleep(10)

    res = VIAVI_get_command(block, ':SENSE:DATA? TEST:SUMMARY', "vc-4", dev, p_dev)
    assert res == '"normal"', f"Трафик не в норме до вставки ошибок: {res}"
    await asyncio.sleep(1)
    VIAVI_set_command(block, ":SOURce:PAYLOAD:BERT:INSert:TSE", "", "vc-4", dev, p_dev)
    await asyncio.sleep(2)

    status = VIAVI_get_command(block, ':SENSE:DATA? TEST:SUMMARY:STATUS', "vc-4", dev, p_dev)
    assert "BitErrorCount" in status, f"Прибор не зафиксировал BitErrorCount. Статус: {status}"

    count_err = VIAVI_get_command(block, ':SENSE:DATA? ECOUNT:PAYLOAD:BERT:TSE', "vc-4", dev, p_dev)
    assert count_err == "1", f"Ожидали 1 ошибку, прибор показал: {count_err}"


async def generate_params():
    params = []
    for w in OIDS_VIAVI["wiring"]:
        if "STM" not in w["dev_interface"]:
            continue
        slot, port = int(w["dev_slot"]), int(w["dev_port"])
        if str(slot) in OIDS_SNMP["active_slots"]:
            alarm = await check_alarmPH(slot, port)
            if str(alarm) in ["1", "2"]:
                continue
            slot_key = oidsSNMP()["slots_dict"][w["dev_slot"]]
            max_vc4 = OIDS["blockOID"]["quantCnctPort"][slot_key]
            for vc4 in range(1, max_vc4 + 1):
                for vc12 in range(1, 64):
                    params.append((w, vc4, vc12))
    return params


TEST_DATA = asyncio.run(generate_params())
test_ids_vc12 = [
    f"Slot:{w['dev_slot']}-Port:{w['dev_port']}-VC4:{vc4}-VC12:{vc12}"
    for w, vc4, vc12 in TEST_DATA
]


@pytest.mark.asyncio
@pytest.mark.parametrize("w, vc4, vc12", TEST_DATA, ids=test_ids_vc12)
async def test_commutationsVC12(w, vc4, vc12):
    slot, port = str(w["dev_slot"]), str(w["dev_port"])
    block, dev, p_dev = w["viavi_interface"], w["viavi_device"], w["viavi_port"]

    await delete_commutation()
    await create_commutationVC12(int(slot), int(port), vc4, vc12)

    klm = klm_numbers(vc12).split(".")
    VIAVI_secndStage(vc="vc-12", device_name=dev, port_name=p_dev)

    cmds = [
        f":SENSE:SDH:CHANNEL:STMN {vc4}",
        f":SENSE:SDH:DS1:E1:LP:C3:CHANNEL {klm[0]}",
        f":SENSE:SDH:DS1:E1:LP:C2:CHANNEL {klm[1]}",
        f":SENSE:SDH:DS1:E1:LP:C12:CHANNEL {klm[2]}",
        ":OUTPUT:CLOCK:SOURCE RECOVERED", ":ABORt"
    ]
    VIAVI_set_command(block, ";".join(cmds), "", "vc-12", dev, p_dev)

    await asyncio.sleep(1)
    VIAVI_set_command(block, ":INITiate", " ", "vc-12", dev, p_dev)

    await asyncio.sleep(7)

    assert await check_alarm_cnct(slot, port, vc4) == 0

    res = VIAVI_get_command(block, ':SENSE:DATA? TEST:SUMMARY', "vc-12", dev, p_dev)
    assert res == '"normal"', f"Трафик не в норме: {res}"

    VIAVI_set_command(block, ":SOURce:PAYLOAD:BERT:INSert:TSE", "", "vc-12", dev, p_dev)
    await asyncio.sleep(3)

    err_count = VIAVI_get_command(block, ':SENSE:DATA? ECOUNT:PAYLOAD:BERT:TSE', "vc-12", dev, p_dev)
    assert err_count == "1", f"Ожидали 1 ошибку, прибор показал: {err_count}"


TEST_PARAMS = [
    ((slot, vc), f"Slot:{slot}-VC12:{vc}")
    for slot, val in oidsSNMP()["slots_dict"].items()
    if "E1" in val and str(slot) in OIDS_SNMP.get("active_slots", {})
    for vc in range(1, OIDS["blockOID"]["quantPort"][val] + 1)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "slot, vc",
    [p[0] for p in TEST_PARAMS],
    ids=[p[1] for p in TEST_PARAMS]
)
async def test_commutationsE1(slot, vc):
    node = next(w for w in OIDS_VIAVI["wiring"] if "STM" in w["dev_interface"])
    v_device, v_port, block = node["viavi_device"], node["viavi_port"], node["viavi_interface"]
    slot_stm, port_stm = int(node["dev_slot"]), int(node["dev_port"])
    await snmp_set(f"{OIDS["loopbackOID"][OIDS_SNMP["slots_dict"][slot]]}{slot}.{vc}", Integer(1))
    VIAVI_secndStage(vc="E1", device_name=v_device, port_name=v_port)
    await delete_commutation()
    await create_commutationE1(slot, vc, slot_stm, port_stm)
    cmds = [
        f":SENSE:SDH:CHANNEL:STMN {1}",
        f":SENSE:SDH:DS1:E1:LP:C3:CHANNEL {1}",
        f":SENSE:SDH:DS1:E1:LP:C2:CHANNEL {1}",
        f":SENSE:SDH:DS1:E1:LP:C12:CHANNEL {1}",
        f":SENSE:PDH:E1:FRAMING UNFR",
        ":OUTPUT:CLOCK:SOURCE RECOVERED", ":ABORt"
    ]
    VIAVI_set_command(block, ";".join(cmds), "", "E1", v_device, v_port)

    await asyncio.sleep(1)
    VIAVI_set_command(block, ":INITiate", "", "E1", v_device, v_port)

    await asyncio.sleep(7)

    assert await check_alarm_cnctE1(slot, vc) in [0, 64]

    res = VIAVI_get_command(block, ':SENSE:DATA? TEST:SUMMARY', "E1", v_device, v_port)
    assert res == '"normal"', f"Трафик не в норме: {res}"

    VIAVI_set_command(block, ":SOURce:PAYLOAD:BERT:INSert:TSE", "", "E1", v_device, v_port)
    await asyncio.sleep(3)

    err_count = VIAVI_get_command(block, ':SENSE:DATA? ECOUNT:PAYLOAD:BERT:TSE', "E1", v_device, v_port)
    assert err_count == "1", f"Ожидали 1 ошибку, прибор показал: {err_count}"
