import asyncio

from MainConnectFunc import *
from pysnmp.hlapi.asyncio import ObjectIdentifier, Integer, OctetString


def KAD_reg_sync(num) -> int:
    return hex(0x0d00 + (num - 1) * 0x100)[2:-1]


def E1_reg_sync(num) -> int:
    return format(num, "02X")


def STM_reg_sync(slot, port) -> str:
    value = 0x0400 + (int(slot) - 17) * 0x400 + (int(port) - 1) * 0x100
    return f"{value:3X}"[:-1]



def STM_extport_sync(slot: int, port: int) -> int:
    return str((int(slot) - 17) * 4 + int(port))

