import time

import paramiko
import pysnmp
from Vivavi.ViaviControl import *
from MainConnectFunc import *
import asyncio
from pysnmp.hlapi.asyncio import ObjectIdentifier, Integer
# print(VIAVI_get_command("Eth10/100", ":SENSe:DATA? RATE:MAC:ETH:MBPS", "vc-12", "NumOne", "Port1"))
# VIAVI_set_command("Eth10/100", ":SOURCE:MAC:ETH:ERROR:TYPE","BURST", "vc-12", "NumOne", "Port1")
# VIAVI_set_command("Eth10/100", ":SOURCE:MAC:ETH:ERROR:QUANTITY","1000", "vc-12", "NumOne", "Port1")
# VIAVI_set_command("Eth10/100", ":SOURCE:MAC:ETH:INSERT:FCS", "", "vc-12", "NumOne", "Port1")

# val = asyncio.run(snmp_get(f"{oids()["statistic"]["Eth_port_stat"]["current15m"]["Eth10/100"]}5.4"))


def snmp_stat_eth_parser(value):
    if isinstance(value, str):
        raw = bytes.fromhex(value.replace(':', ''))
    else:
        raw = value.asOctets()

    res = [
        int(raw[0:1].hex()),
        int.from_bytes(raw[1:4], 'little'),  # ES (3 байта)
        int.from_bytes(raw[4:7], 'little'),  # SES (3 байта)
        int.from_bytes(raw[7:10], 'little'),  # UAS (3 байта)
        int.from_bytes(raw[16:22], 'little'),  # FCS (6 байт)
        int.from_bytes(raw[10:16], 'little'),  # Received (6 байт)
        int.from_bytes(raw[22:28], 'little'),  # Discarded (6 байт)
        int.from_bytes(raw[32:36], 'little')  # Elapsed (4 байта)
    ]
    return res


async def first_test_func(count_fcs):
    await snmp_set(f"{oids()['statistic']['Eth_port_stat']['reset']['Eth10/100']}5.3", Integer(1))

    VIAVI_set_command("Eth10/100", ":SOURCE:MAC:ETH:ERROR:QUANTITY", f"{count_fcs}", "vc-12", "NumOne", "Port1")
    VIAVI_set_command("Eth10/100", ":SOURCE:MAC:ETH:INSERT:FCS", "", "vc-12", "NumOne", "Port1")

    await asyncio.sleep(1)

    val = await snmp_get(f"{oids()['statistic']['Eth_port_stat']['current15m']['Eth10/100']}5.3")
    parsed_stats = snmp_stat_eth_parser(val)

    assert parsed_stats[4] == count_fcs, f"Ошибка: Ожидали {count_fcs}, получили {parsed_stats[4]}"


    VIAVI_set_command("Eth10/100", ":SOURCE:MAC:ETH:ERROR:QUANTITY", f"{count_fcs}", "vc-12", "NumOne", "Port1")
    VIAVI_set_command("Eth10/100", ":SOURCE:MAC:ETH:INSERT:FCS", "", "vc-12", "NumOne", "Port1")

    await asyncio.sleep(1)

    val = await snmp_get(f"{oids()['statistic']['Eth_port_stat']['current15m']['Eth10/100']}5.3")
    parsed_stats = snmp_stat_eth_parser(val)

    assert parsed_stats[4] == count_fcs * 2, f"Ошибка: Ожидали {count_fcs * 2}, получили {parsed_stats[4]}"


# if __name__ == "__main__":
    asyncio.run(first_test_func(4567))