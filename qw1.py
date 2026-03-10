# async def zcatExtSource():
#     for i in range(1, 100):
#         for z in range(1, 3):
#             await snmp_set(
#                 f"1.3.6.1.4.1.5756.3.3.1.2.3.5.1.5.{z}",
#                 ObjectIdentifier("1.3.6.1.4.1.5756.3.3.2.18.2.4.2.1.3.8.1"),
#             )
#
#         await asyncio.sleep(8)
#
#         slot = "08"
#         val = await asyncio.to_thread(get_ssh_value, slot)
#         print(val.split()[-1][:-1])
#         if val.split()[-1][:-1] != "17":
#             print(f"Ошибка в слоту {slot}")
#             break
#
#         for x in range(1, 3):
#             await snmp_set(
#                 f"1.3.6.1.4.1.5756.3.3.1.2.3.5.1.5.{x}",
#                 ObjectIdentifier("1.3.6.1.4.1.5756.3.3.2.19.2.4.2.1.3.13.1"),
#             )
#
#         await asyncio.sleep(8)
#
#         slot = "13"
#         val = await asyncio.to_thread(get_ssh_value, slot)
#         print(val.split()[-1][:-1])
#         if val.split()[-1][:-1] != "17":
#             print(f"Ошибка в слоту {slot}")
#             break
#
#         print(f"Count - {i}")
#         await asyncio.sleep(8)


# if __name__ == "__main__":
#     asyncio.run(zcatExtSource())


import asyncio
import time
import paramiko
import re
from pysnmp.hlapi.asyncio import (
    SnmpEngine, UsmUserData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity, set_cmd
)
from pysnmp.hlapi.asyncio import ObjectIdentifier
import libconf


def get_ssh_value(PM) -> str:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("192.168.120.146", port=22, username="root", password="")
    stdin, stdout, stderr = ssh.exec_command(
        f'zcat /var/volatile/tmp/osmkm/config/PM{PM}.INI.cfg.gz | grep ExtSyncr'
    )
    result = stdout.read().decode()
    ssh.close()
    return result.strip()


async def snmp_set(oid: str, value):
    error_indication, error_status, error_index, var_binds = await set_cmd(
        SnmpEngine(),
        UsmUserData("admin"),
        await UdpTransportTarget.create(("localhost", 1161)),
        ContextData(),
        ObjectType(ObjectIdentity(oid), value),
    )

    if error_indication:
        raise RuntimeError(f"SNMP error_indication: {error_indication}")
    if error_status:
        raise RuntimeError(f"SNMP error_status: {error_status.prettyPrint()} at {error_index}")

    return var_binds[0][1]


EXT_SRC_OID_BASE = "1.3.6.1.4.1.5756.3.3.1.2.3.5.1.5"
SLOT_8_OID = ObjectIdentifier("1.3.6.1.4.1.5756.3.3.2.18.2.4.2.1.3.8.1")
SLOT_13_OID = ObjectIdentifier("1.3.6.1.4.1.5756.3.3.2.19.2.4.2.1.3.13.1")

EXPECTED_STATUS = "17"

EXT_SOURCES = range(1, 3)


def _extract_last_number(text: str) -> str | None:
    nums = re.findall(r"\d+", text)
    return nums[-1] if nums else None


async def _set_ext_sources(profile_oid: ObjectIdentifier) -> None:
    for src in EXT_SOURCES:
        await snmp_set(f"{EXT_SRC_OID_BASE}.{src}", profile_oid)


async def _check_slot(slot: str) -> bool:
    val = await asyncio.to_thread(get_ssh_value, slot)
    last_num = _extract_last_number(val)

    if last_num != EXPECTED_STATUS:
        print(f"Ошибка в слоту {slot}: ожидали {EXPECTED_STATUS}, получили {last_num!r}. Ответ: {val!r}")
        return False
    return True


async def zcatExtSource(iterations: int = 99) -> None:
    for i in range(1, iterations + 1):
        await _set_ext_sources(SLOT_8_OID)
        await asyncio.sleep(2)

        if not await _check_slot("08"):
            break
        await _set_ext_sources(SLOT_13_OID)
        await asyncio.sleep(2)

        if not await _check_slot("13"):
            break

        print(f"Count - {i}")
        await asyncio.sleep(2)


asyncio.run(zcatExtSource())
