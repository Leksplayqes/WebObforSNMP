from Osmk_category import *
import pytest
from MainConnectFunc import oidsSNMP
import asyncio


def as_list(raw):
    return raw if isinstance(raw, list) else [raw]


@pytest.fixture(scope="module")
def device_reload():
    device_reboot()
    yield


# ----------------------------
# TESTS: Category blocks
# ----------------------------
@pytest.mark.parametrize("slot, block",
                         [(s, b) for s, b in oidsSNMP()["slots_dict"].items() if s in EQ["active_slots"]])
def test_set_block_category(slot, block):
    block_data = CATEGORY_BLOCKS_DB[block]
    asyncio.run(process_category_block(SLOTS_DICT, block, block_data))
    result = asyncio.run(reading_category_block(SLOTS_DICT, block, block_data))
    for key, raw in result.items():
        val = bytes_from_snmp_value(raw)
        assert not any(d in val for d in [b"\x00", b"\x01", b"\x02", b"\x03", b"\x05"]), f"{key}={val!r}"
    status = asyncio.run(config_block_equipment(slot))
    assert status is True, f"Обнаружены ошибки в конфигурационном файле: {status}"


@pytest.mark.parametrize("slot, block", oidsSNMP()["slots_dict"].items())
def test_check_block_category(device_reload, slot, block):
    block_data = CATEGORY_BLOCKS_DB[block]
    new_result = asyncio.run(reading_category_block(SLOTS_DICT, block, block_data))
    for key, raw in new_result.items():
        val = bytes_from_snmp_value(raw)
        assert not any(d in val for d in [b"\x00", b"\x01", b"\x02", b"\x03", b"\x05"]), f"{key}={val!r}"
    status = asyncio.run(config_block_equipment(slot))
    assert status is True, f"Обнаружены ошибки в конфигурационном файле: {status}"


# ----------------------------
# TESTS: Category equipment
# ----------------------------
def test_set_equipment_category():
    if not EQUIPMENT_DATA:
        pytest.skip("No equipment OIDs in Category")
    asyncio.run(process_category_equipment(EQUIPMENT_DATA))
    result = asyncio.run(reading_category_equipment(EQUIPMENT_DATA))
    print(result)
    for key, raw in result.items():
        val = bytes_from_snmp_value(raw)
        assert not any(d in val for d in [b"\x00", b"\x01", b"\x02", b"\x03", b"\x05"]), f"{key}={val!r}"
    status = asyncio.run(config_category_equipment())
    assert status is True, f"Обнаружены ошибки в конфигурационном файле: {status}"


def test_check_equipment_category(device_reload):
    if not EQUIPMENT_DATA:
        pytest.skip("No equipment OIDs in Category")

    new_result = asyncio.run(reading_category_equipment(EQUIPMENT_DATA))

    for key, raw in new_result.items():
        val = bytes_from_snmp_value(raw)
        assert not any(d in val for d in [b"\x00", b"\x01", b"\x02", b"\x03", b"\x05"]), f"{key}={val!r}"
    status = asyncio.run(config_category_equipment())
    assert status is True, f"Обнаружены ошибки в конфигурационном файле: {status}"


# ----------------------------
# TESTS: Category sync
# ----------------------------
@pytest.mark.parametrize("priornum", range(1, 9))
def test_set_sync_category(priornum):
    if not SYNC_DATA:
        pytest.skip("No equipment OIDs in Category")
    asyncio.run(process_category_sync(SYNC_DATA, priornum))
    result = asyncio.run(reading_category_sync(SYNC_DATA, priornum))

    for key, raw in result.items():
        val = bytes_from_snmp_value(raw)
        assert b"\x04" in val, f"Ожидалась 4 в {key}, получено {val!r}"

    status = asyncio.run(config_category_sync())
    assert status is True, f"Обнаружены ошибки в конфигурационном файле: {status}"


@pytest.mark.parametrize("priornum", range(1, 9))
def test_check_sync_category(device_reload, priornum):
    if not SYNC_DATA:
        pytest.skip("No equipment OIDs in Category")

    new_result = asyncio.run(reading_category_sync(SYNC_DATA, priornum))

    for key, raw in new_result.items():
        val = bytes_from_snmp_value(raw)
        assert not any(d in val for d in [b"\x00", b"\x01", b"\x02", b"\x03", b"\x05"]), f"{key}={val!r}"

    status = asyncio.run(config_category_sync())
    assert status is True, f"Обнаружены ошибки в конфигурационном файле: {status}"


# ----------------------------
# TESTS: Label
# ----------------------------
@pytest.mark.parametrize("slot, block", oidsSNMP()["slots_dict"].items())
def test_set_label(slot, block):
    if block not in LABEL_BLOCKS_DB:
        pytest.skip("No Label OIDs for this block")

    block_data = LABEL_BLOCKS_DB[block]
    asyncio.run(process_label_block(SLOTS_DICT, block, block_data))
    result = asyncio.run(reading_label_block(SLOTS_DICT, block, block_data))

    for key, raw in result.items():
        slot_in_key = int(key.split("@slot")[1])
        expected = f"{block}-{slot_in_key}"
        for v in as_list(raw):
            assert v == expected

    status = asyncio.run(config_label(slot, block))
    assert status is True, f"Обнаружены ошибки в конфигурационном файле: {status}"


@pytest.mark.parametrize("slot, block", oidsSNMP()["slots_dict"].items())
def test_check_label(device_reload, slot, block):
    if block not in LABEL_BLOCKS_DB:
        pytest.skip("No Label OIDs for this block")

    block_data = LABEL_BLOCKS_DB[block]
    result = asyncio.run(reading_label_block(SLOTS_DICT, block, block_data))

    for key, raw in result.items():
        slot_in_key = int(key.split("@slot")[1])
        expected = f"{block}-{slot_in_key}"
        for v in as_list(raw):
            assert v == expected

    status = asyncio.run(config_label(slot, block))
    assert status is True, f"Обнаружены ошибки в конфигурационном файле: {status}"


# ----------------------------
# TESTS: Mask
# ----------------------------
@pytest.mark.parametrize("slot, block", oidsSNMP()["slots_dict"].items())
def test_set_mask(slot, block):
    if block not in MASK_BLOCKS_DB:
        pytest.skip("No Mask OIDs for this block")

    block_data = MASK_BLOCKS_DB[block]
    asyncio.run(process_mask_block(SLOTS_DICT, block, block_data))
    result = asyncio.run(reading_mask_block(SLOTS_DICT, block, block_data))
    for key, raw in result.items():
        for v in as_list(raw):
            assert int(v) == 1, f"{key}={v!r}"

    status = asyncio.run(config_mask(slot))
    assert status is True, f"Обнаружены ошибки в конфигурационном файле: {status}"


@pytest.mark.parametrize("slot, block", oidsSNMP()["slots_dict"].items())
def test_check_mask(device_reload, slot, block):
    if block not in MASK_BLOCKS_DB:
        pytest.skip("No Mask OIDs for this block")

    block_data = MASK_BLOCKS_DB[block]
    result = asyncio.run(reading_mask_block(SLOTS_DICT, block, block_data))
    for key, raw in result.items():
        for v in as_list(raw):
            assert int(v) == 1, f"{key}={v!r}"

    status = asyncio.run(config_mask(slot))
    assert status is True, f"Обнаружены ошибки в конфигурационном файле: {status}"


# ----------------------------
# TESTS: Loop
# ----------------------------
@pytest.mark.parametrize("slot, block", filter(
    lambda item: "STM" in item[1] or "E1" in item[1], oidsSNMP()["slots_dict"].items()))
@pytest.mark.parametrize("loop_value", [1, 2])
def test_set_loop(slot, block, loop_value):
    if block not in LOOP_BLOCKS_DB:
        pytest.skip("No Loop OIDs for this block")

    block_data = LOOP_BLOCKS_DB[block]
    asyncio.run(process_loop_block(SLOTS_DICT, block, block_data, loop_value))
    result = asyncio.run(reading_loop_block(SLOTS_DICT, block, block_data))

    for key, raw in result.items():
        for v in as_list(raw):
            assert int(v) == loop_value, f"{key}={v!r}"

    status = asyncio.run(config_loop(slot))
    assert status is True, f"Обнаружены ошибки в конфигурационном файле: {status}"


@pytest.mark.parametrize("slot, block", filter(
    lambda item: "STM" in item[1] or "E1" in item[1], oidsSNMP()["slots_dict"].items()))
@pytest.mark.parametrize("loop_value", [1, 2])
def test_check_loop(device_reload, slot, block, loop_value):
    if block not in LOOP_BLOCKS_DB:
        pytest.skip("No Loop OIDs for this block")

    block_data = LOOP_BLOCKS_DB[block]
    result = asyncio.run(reading_loop_block(SLOTS_DICT, block, block_data))

    for key, raw in result.items():
        for v in as_list(raw):
            assert int(v) == loop_value, f"{key}={v!r}"

    status = asyncio.run(config_loop(slot))
    assert status is True, f"Обнаружены ошибки в конфигурационном файле: {status}"


# ----------------------------
# TESTS: Trace
# ----------------------------
@pytest.mark.parametrize("slot, block", oidsSNMP()["slots_dict"].items())
def test_set_trace(slot, block):
    if block not in TRACE_BLOCKS_DB:
        pytest.skip("No Trace OIDs for this block")

    block_data = TRACE_BLOCKS_DB[block]
    asyncio.run(process_trace_block(SLOTS_DICT, block, block_data))
    result = asyncio.run(reading_trace_block(SLOTS_DICT, block, block_data))

    for key, raw in result.items():
        slot_in_key = int(key.split("@slot")[1])
        expected = (f"{block}-{slot_in_key}"[:15]).ljust(15)

        for v in as_list(raw):
            assert isinstance(v, str)
            assert len(v) == 15
            assert v == expected

    status = asyncio.run(config_trace(slot, block))
    assert status is True, f"Обнаружены ошибки в конфигурационном файле: {status}"


@pytest.mark.parametrize("slot, block", oidsSNMP()["slots_dict"].items())
def test_check_trace(device_reload, slot, block):
    if block not in TRACE_BLOCKS_DB:
        pytest.skip("No Trace OIDs for this block")

    block_data = TRACE_BLOCKS_DB[block]
    result = asyncio.run(reading_trace_block(SLOTS_DICT, block, block_data))

    for key, raw in result.items():
        slot_in_key = int(key.split("@slot")[1])
        expected = (f"{block}-{slot_in_key}"[:15]).ljust(15)

        for v in as_list(raw):
            assert isinstance(v, str)
            assert len(v) == 15
            assert v == expected

    status = asyncio.run(config_trace(slot, block))
    assert status is True, f"Обнаружены ошибки в конфигурационном файле: {status}"
