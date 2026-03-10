import asyncio
import json
import datetime
import time

import pytest

from Opp_category import reading_block, process_block
from Opp_mainSettings import get_blockList, oid, device_reboot, cli_set_category
from Opp_mask import mask_reading_block, mask_process_block
from Opp_relay_label import label_process_block, label_reading_block


@pytest.fixture(scope="module")
def get_block_data_fixture():
    block_list = asyncio.run(get_blockList())
    oid["DevSettings"]["BlockList"] = block_list
    with open("OppCategory.json", "w") as block:
        json.dump(oid, block)
    time.sleep(1)


@pytest.fixture(scope="module")
def device_reload():
    device_reboot()
    yield


@pytest.mark.parametrize('block',
                         [block
                          for block in oid["DevSettings"]["BlockList"] if block != "Free"
                          ])
def test_set_opp_block_category(get_block_data_fixture, block):
    block_data = oid["Category"][block]
    asyncio.run(process_block(block, block_data, oid["DevSettings"]["BlockList"]))
    result = asyncio.run(reading_block(block, block_data, oid["DevSettings"]["BlockList"]))
    for value in result:
        assert not any(dig in result[value] for dig in [b"\x00", b"\x01", b"\x02", b"\x03", b"\x04"]), f"{value} = {result[value]}"


@pytest.mark.parametrize('block',
                         [block
                          for block in oid["DevSettings"]["BlockList"] if block != "Free"])
def test_check_opp_block_category(device_reload, block):
    block_data = oid["Category"][block]
    new_result = asyncio.run(reading_block(block, block_data, oid["DevSettings"]["BlockList"]))
    for value in new_result:
        assert not any(dig in new_result[value] for dig in [b"\x00", b"\x01", b"\x02", b"\x03", b"\x04"]), f"{value} = {new_result[value]}"


@pytest.mark.parametrize('block',
                         [block
                          for block in oid["DevSettings"]["BlockList"] if block not in ["Free"]])
def test_cli_opp_set_category(get_block_data_fixture, block):
    cli_set_category(oid["DevSettings"]["BlockList"][block], block)
    time.sleep(0.5)
    result = asyncio.run(reading_block(block, oid["Category"][block], oid["DevSettings"]["BlockList"]))
    for value in result:
        assert not any(dig in result[value] for dig in [b"\x00", b"\x01", b"\x02", b"\x03", b"\x05"]), f"{value} = {result[value]}"


@pytest.mark.parametrize('block', [block
                                   for block in oid["DevSettings"]["BlockList"] if block not in ["Free"]])
def test_cli_opp_check_category(device_reload, block):
    result = asyncio.run(reading_block(block, oid["Category"][block], oid["DevSettings"]["BlockList"]))
    for value in result:
        assert not any(dig in result[value] for dig in [b"\x00", b"\x01", b"\x02", b"\x03", b"\x05"]), f"{value} = {result[value]}"


@pytest.mark.parametrize('block', [block
                                   for block in oid["DevSettings"]["BlockList"] if
                                   block not in ["MVPv1", 'MASv1', "MV2Mv1", "Free", "ROADMv1", "DWDM40v1", "DWDM401v1", "TP410Gv1"]])
def test_set_opp_block_mask(get_block_data_fixture, block):
    block_data = oid["MaskAlarm"][block]
    asyncio.run(mask_process_block(block, block_data, oid["DevSettings"]["BlockList"]))
    result = asyncio.run(mask_reading_block(block, block_data, oid["DevSettings"]["BlockList"]))
    for value in result:
        assert result[value] == 0


@pytest.mark.parametrize('block', [block
                                   for block in oid["DevSettings"]["BlockList"] if
                                   block not in ["MVPv1", 'MASv1', "MV2Mv1", "Free", "ROADMv1", "DWDM40v1", "DWDM401v1", "TP410Gv1"]])
def test_check_opp_block_mask(device_reload, block):
    block_data = oid["MaskAlarm"][block]
    result = asyncio.run(mask_reading_block(block, block_data, oid["DevSettings"]["BlockList"]))
    for value in result:
        assert result[value] == 0


@pytest.mark.parametrize('block', [block
                                   for block in oid["DevSettings"]["BlockList"] if
                                   block not in ["MV2Mv1", "Free", "MVPv1", "TP410Gv1"]])
def test_set_opp_block_label(get_block_data_fixture, block):
    block_data = oid["RelayLabel"][block]
    asyncio.run(label_process_block(block, block_data, oid["DevSettings"]["BlockList"]))
    result = asyncio.run(label_reading_block(block, block_data, oid["DevSettings"]["BlockList"]))
    for value in result:
        assert result[value].decode("utf-8") == f"{datetime.datetime.now().date()}_{block}", f"{value}={result[value]}"


@pytest.mark.parametrize('block', [block
                                   for block in oid["DevSettings"]["BlockList"] if
                                   block not in ["MV2Mv1", "Free", "MVPv1", "TP410Gv1"]])
def test_check_opp_block_label(device_reload, block):
    block_data = oid["RelayLabel"][block]
    result = asyncio.run(label_reading_block(block, block_data, oid["DevSettings"]["BlockList"]))
    for value in result:
        assert result[value].decode("utf-8") == f"{datetime.datetime.now().date()}_{block}", f"{value}={result[value]}"
