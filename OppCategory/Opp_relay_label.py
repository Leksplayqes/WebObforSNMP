import asyncio
import datetime

from puresnmp.types import OctetString

from Opp_mainSettings import client, set_oid_value, get_oid_value, get_blockList
from Opp_mainSettings import oid as ID


def get_block_data():
    block_list = asyncio.run(get_blockList())
    for block in block_list:
        if block not in ["MV2Mv1", "Free", "MVPv1"]:
            block_data = ID["RelayLabel"][block]


async def cli_process_block(block, block_list):
    pass


async def label_process_block(block, block_data, block_list):
    client_instance = client()
    current_date = datetime.datetime.now().date()
    slot_quant = ID['DevSettings']["SlotQuantRelayLabel"][block]
    block_index = block_list[block]

    value = f"{current_date}_{block}".encode("ascii")
    octet_value = OctetString(value)

    tasks = []

    for obj, (oid, depth) in block_data.items():
        if depth == 1:
            oid_path = f"{oid}{block_index}"
            tasks.append(set_oid_value(client_instance, oid_path, octet_value))
        elif depth == 2:
            for port in range(1, slot_quant + 1):
                oid_path = f"{oid}{block_index}.{port}"
                tasks.append(set_oid_value(client_instance, oid_path, octet_value))
        else:
            txrx_range = range(1, 3)
            evenodd_range = range(1, 3) if block != 'DWDM40v1' else (1,)

            for port in range(1, slot_quant + 1):
                for txrx in txrx_range:
                    for evenodd in evenodd_range:
                        oid_path = f"{oid}{block_index}.{txrx}.{evenodd}.{port}"
                        tasks.append(set_oid_value(client_instance, oid_path, octet_value))
    await asyncio.gather(*tasks)


async def label_reading_block(block, block_data, block_list):
    client_instance = client()
    slot_quant = ID['DevSettings']["SlotQuantRelayLabel"][block]
    block_index = block_list[block]

    oid_paths = []
    for obj, (oid, depth) in block_data.items():
        if depth == 1:
            oid_paths.append(f"{oid}{block_index}")
        elif depth == 2:
            for port in range(1, slot_quant + 1):
                oid_paths.append(f"{oid}{block_index}.{port}")
        else:
            txrx_range = range(1, 3)
            evenodd_range = range(1, 3) if block != 'DWDM40v1' else (1,)
            for port in range(1, slot_quant + 1):
                for txrx in txrx_range:
                    for evenodd in evenodd_range:
                        oid_paths.append(f"{oid}{block_index}.{txrx}.{evenodd}.{port}")
    tasks = [get_oid_value(client_instance, oid_path) for oid_path in oid_paths]
    values = await asyncio.gather(*tasks)

    return dict(zip(oid_paths, values))