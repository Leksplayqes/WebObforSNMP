import asyncio
import datetime
import os
import time
from pysnmp.hlapi import *
from pysnmp.hlapi.asyncio import *
from MainConnectFunc import oids, oidsSNMP, snmp_set, snmp_get, snmp_set_bulk, snmp_getBulk, equpimentV7, multi_snmp_get
import paramiko
from MainConnectFunc import oids as get_oids
from MainConnectFunc import oidsSNMP as get_oids_snmp
from MainConnectFunc import oidsVIAVI as get_viavi_oids
from MainConnectFunc import find_KS, snmp_get, snmp_set

OIDS_SNMP = get_oids_snmp()
OIDS = get_oids()
OIDS_VIAVI = get_viavi_oids()
SLOTS_DICT = OIDS_SNMP.get("slots_dict", {})
KC_SLOT = find_KS()


# from unit_tests.sshV7 import ssh_reload


def slot_to_block(slot):
    block = oidsSNMP()["slots_dict"][slot]
    return block


def check_loopback():
    for key in oidsSNMP()["slots_dict"]:
        if key == str(oidsSNMP()["loopback"]["slot"]):
            return [str(oidsSNMP()["loopback"]["slot"]), str(oidsSNMP()["loopback"]["port"])]
        else:
            continue


def set_E1_loopback():
    for slot in [slot for slot in oidsSNMP()["slots_dict"] if
                 "E1" in oidsSNMP()["slots_dict"][slot]]:
        if len([[f"{oids()['loopbackOID'][oidsSNMP()['slots_dict'][slot]]}{slot}.{port}", 1] for port in
                range(1, oids()["blockOID"]["quantPort"][oidsSNMP()["slots_dict"][slot]] + 1)]) > 7:
            for lenth in range(7, oids()["blockOID"]["quantPort"][oidsSNMP()["slots_dict"][slot]] + 1, 7):
                asyncio.run(snmp_set_bulk(
                    [[f"{oids()['loopbackOID'][oidsSNMP()['slots_dict'][slot]]}{slot}.{port}", 1] for port in
                     range(1, oids()["blockOID"]["quantPort"][oidsSNMP()["slots_dict"][slot]] + 1)][lenth - 7:lenth]))


def klm_numbers(vc12):
    x = []
    for k in range(1, 4):
        for l in range(1, 8):
            for m in range(1, 4):
                x.append(f'{k}.{l}.{m}')
    return x[vc12 - 1]


def klm_numbersE1(vc12):
    x = []
    for m in range(1, 4):
        for l in range(1, 8):
            for k in range(1, 4):
                x.append(f'{k}.{l}.{m}')
    return x[vc12 - 1]


def klm_numbersETH(vc12):
    x = []
    for k in range(1, 4):
        for l in range(1, 8):
            for m in range(1, 4):
                x.append(f'{k}.{l}.{m}')
    return x[vc12 - 1]


def klm_numbersEth100M(vc12):
    sequence = []
    for k in range(1, 4):
        for l in range(1, 8):
            if l == 1 or (l == 2 and k == 1):
                max_m = 4
            else:
                max_m = 3
            for m in range(1, max_m):
                sequence.append(f"{k}.{l}.{m}")
    if 1 <= vc12 <= len(sequence):
        return sequence[vc12 - 1]
    return None


''' На всех слотах STM, E1, что есть в idReal, включается анализ на физических портах'''

''' ДЛЯ СМД2 нужно придумоать заглушку на включение аланила при заблокированных портах СТМ, мб поменять bulk_set на простой set'''


async def alarmplusmask():
    for slot in oidsSNMP()["slots_dict"]:
        if 'STM' in oidsSNMP()["slots_dict"][slot] or 'E1' in oidsSNMP()["slots_dict"][slot]:
            await snmp_set_bulk(
                [(oids()['main_alarm']['alarmMODE'][oidsSNMP()['slots_dict'][slot]] + slot + f'.{port}', Integer(2))
                 for port in range(1, oids()["blockOID"]['quantPort'][oidsSNMP()['slots_dict'][slot]] + 1)])


async def alarmplusmaslcnctSTM():
    for slot in oidsSNMP()["slots_dict"]:
        if 'STM' in oidsSNMP()["slots_dict"][slot]:
            allSets = ([(oids()['main_alarm']["alarmMODEcnct"][oidsSNMP()['slots_dict'][slot]] + slot + f'.{port}.{vc}',
                         Integer(2))
                        for port in range(1, oids()["blockOID"]['quantPort'][oidsSNMP()['slots_dict'][slot]] + 1)
                        for vc in range(1, oids()["blockOID"]["quantCnctPort"][oidsSNMP()['slots_dict'][slot]] + 1)])
            await snmp_set_bulk(allSets)
        elif 'E1' in oidsSNMP()["slots_dict"][slot]:
            allSets = ([(oids()['main_alarm']["alarmMODEcnct"][
                             oidsSNMP()['slots_dict'][slot]] + slot + '.1.1.' + f'{klm_numbersE1(vc)}', Integer(2))
                        for vc in range(1, oids()["blockOID"]["quantCnctPort"][oidsSNMP()['slots_dict'][slot]] + 1)])
            await snmp_set_bulk(allSets)


async def check_alarmPH(slot, portnum):
    alarm = await snmp_get(
        f'{oids()["main_alarm"]["alarm_status"]["physical"][oidsSNMP()["slots_dict"][str(slot)]] + str(slot) + f".{portnum}"}')
    return alarm


async def setSFP_Mode():
    for slot in oidsSNMP()["slots_dict"]:
        if 'STM' in oidsSNMP()["slots_dict"][slot]:
            allSetsMode = (
                [(oids()["sfpSettings"]["sfpMODE"][oidsSNMP()['slots_dict'][slot]] + slot + f'.{port}', Integer(2))
                 for port in range(1, oids()["blockOID"]['quantPort'][oidsSNMP()['slots_dict'][slot]] + 1)])
            await snmp_set_bulk(allSetsMode)
            if oidsSNMP()["name"] != "SMD2v2":
                allSetsLock = (
                    [(oids()["sfpSettings"]["sfpCheckMODE"][oidsSNMP()['slots_dict'][slot]] + slot + f'.{port}',
                      Integer(1))
                     for port in range(1, oids()["blockOID"]['quantPort'][oidsSNMP()['slots_dict'][slot]] + 1)])

                await snmp_set_bulk(allSetsLock)

async def check_alarmSFP():
    ttlList = []
    for slot in oidsSNMP()["slots_dict"]:
        if 'STM' in oidsSNMP()["slots_dict"][slot]:
            allGetAlarm = (
                [(oids()["sfpSettings"]["sfpAlarm"][oidsSNMP()['slots_dict'][slot]] + slot + f'.{port}')
                 for port in range(1, oids()["blockOID"]['quantPort'][oidsSNMP()['slots_dict'][slot]] + 1)])
            ttlList.append(await multi_snmp_get(allGetAlarm))
    return sum(ttlList, [])

print(asyncio.run(check_alarmSFP()))

async def check_lockSFP():
    ttlList = []
    for slot in oidsSNMP()["slots_dict"]:
        if 'STM' in oidsSNMP()["slots_dict"][slot]:
            allGetAlarm = (
                [(oids()["sfpSettings"]["sfpCheckAlarm"][oidsSNMP()['slots_dict'][slot]] + slot + f'.{port}')
                 for port in range(1, oids()["blockOID"]['quantPort'][oidsSNMP()['slots_dict'][slot]] + 1)])
            ttlList.append(await multi_snmp_get(allGetAlarm))
    return sum(ttlList, [])
print(asyncio.run(check_lockSFP()))

async def check_alarm_cnct(slot, portnum, vc):
    alarm = await snmp_get(
        f'{oids()["main_alarm"]["alarm_status"]["connective"][oidsSNMP()["slots_dict"][slot]] + f"{slot}" + f".{portnum}" + f".{vc}"}')
    return alarm


async def check_alarm_cnctE1(slot, vc):
    alarm = await snmp_get(
        f'{oids()["main_alarm"]["alarm_status"]["connective"][oidsSNMP()["slots_dict"][slot]] + str(slot) + f".1.1" + f".{klm_numbersE1(vc)}"}')
    return alarm


'''Value must be 15 symbols'''


async def change_traceTD(slot, portnum, value):
    traceTD = await snmp_set(
        f"{oids()['main_alarm']['alarm_setup_oid']['TIM']['TD'][oidsSNMP()['slots_dict'][slot]] + str(slot) + f'.{portnum}'}",
        OctetString(f"{value}"))
    return traceTD


async def change_traceTDE1(slot, portnum, value):
    traceTD = await snmp_set(
        f"{oids()['main_alarm']['alarm_setup_oid']['TIM']['TD'][oidsSNMP()['slots_dict'][slot]] + str(slot) + f'.1.1.{klm_numbersE1(portnum)}'}",
        OctetString(f"{value}"))
    return traceTD


# async def change_traceTDGE(block, vc, value):
#     traceTD = await snmp_set(
#         f"{oids()['main_alarm']['alarm_setup_oid']['TIM']['TD'][block] + str(oidsSNMP()['slots_dict'][block]) + f'.1.{vc}'}",
#         OctetString(f"{value}"))
#     return traceTD


# async def change_traceExpectedGE(block, vc, value):
#     traceTD = await snmp_set(
#         f"{oids()['main_alarm']['alarm_setup_oid']['TIM']['EXPECTED'][block] + str(oidsSNMP()['slots_dict'][block]) + f'.1.{vc}'}",
#         OctetString(f"{value}"))
#     return traceTD


async def change_traceExpected(slot, portnum, value):
    traceTD = await snmp_set(
        f"{oids()['main_alarm']['alarm_setup_oid']['TIM']['EXPECTED'][oidsSNMP()['slots_dict'][slot]] + str(slot) + f'.{portnum}'}",
        OctetString(f"{value}"))
    return traceTD


async def create_commutationVC4(slot, port, vc):
    await snmp_set(
        f"{oids()['switch']['switch_portVC4'][oidsSNMP()['slots_dict'][check_loopback()[0]]] + str(check_loopback()[0]) + '.' + str(oidsSNMP()['loopback']["port"]) + '.1'}",
        ObjectIdentifier(
            f"{oids()['switch']['data_directionVC4'][oidsSNMP()['slots_dict'][str(slot)]] + str(slot) + f'.{port}' + f'.{vc}'}"))
    await snmp_set(
        f"{oids()['switch']['switch_portVC4'][oidsSNMP()['slots_dict'][str(slot)]] + str(slot) + f'.{port}' + f'.{vc}'}",
        ObjectIdentifier(
            f"{oids()['switch']['data_directionVC4'][oidsSNMP()['slots_dict'][check_loopback()[0]]] + str(check_loopback()[0]) + '.' + str(oidsSNMP()['loopback']["port"]) + '.1'}"))


async def create_commutationVC12(slot, port, vc4, vc12):
    await snmp_set(
        f"{oids()['switch']['switch_portVC12'][oidsSNMP()['slots_dict'][str(check_loopback()[0])]] + str(check_loopback()[0]) + '.' + str(oidsSNMP()['loopback']["port"]) + '.1.1.1.1'}",
        ObjectIdentifier(
            f"{oids()['switch']['data_directionVC12'][oidsSNMP()['slots_dict'][str(slot)]] + str(slot) + f'.{port}' + f'.{vc4}' + f'.{klm_numbers(vc12)}'}"))
    await snmp_set(
        f"{oids()['switch']['switch_portVC12'][oidsSNMP()['slots_dict'][str(slot)]] + str(slot) + f'.{port}' + f'.{vc4}' + f'.{klm_numbers(vc12)}'}",
        ObjectIdentifier(
            f"{oids()['switch']['data_directionVC12'][oidsSNMP()['slots_dict'][str(check_loopback()[0])]] + str(check_loopback()[0]) + '.' + str(oidsSNMP()['loopback']["port"]) + '.1.1.1.1'}"))


async def create_commutationGE(block, vc4):
    slot, port = await portViavi()  # STMslot, STMport = oidsSNMP()['loopback']
    await snmp_set(
        f"{oids()['switch']['switch_portVC4'][block] + str(oidsSNMP()['slots_dict'][block]) + '.1.' + f'{vc4}'}",
        ObjectIdentifier(
            f"{oids()['switch']['data_directionVC4'][slot] + str(oidsSNMP()['slots_dict'][slot]) + f'.{port}' + '.1'}"))
    await snmp_set(
        f"{oids()['switch']['switch_portVC4'][slot] + str(oidsSNMP()['slots_dict'][slot]) + f'.{port}' + '.1'}",
        ObjectIdentifier(
            f"{oids()['switch']['data_directionVC4'][block] + str(oidsSNMP()['slots_dict'][block]) + '.1.' + f'{vc4}'}"))


async def create_commutationE1(slot, vc12, STMslot, STMport):
    await snmp_set(
        f"{oids()['switch']['switch_portVC12'][oidsSNMP()['slots_dict'][slot]] + slot + '.1.1.' + f'{klm_numbersE1(vc12)}'}",
        ObjectIdentifier(
            f"{oids()['switch']['data_directionVC12'][oidsSNMP()['slots_dict'][str(STMslot)]] + str(STMslot) + f'.{STMport}' + '.1.1.1.1'}"))
    await snmp_set(
        f"{oids()['switch']['switch_portVC12'][oidsSNMP()['slots_dict'][str(STMslot)]] + str(STMslot) + f'.{STMport}' + '.1.1.1.1'}",
        ObjectIdentifier(
            f"{oids()['switch']['data_directionVC12'][oidsSNMP()['slots_dict'][slot]] + slot + '.1.1.' + f'{klm_numbersE1(vc12)}'}"))


async def delete_commutation(oid):
    await snmp_set(oid, Integer(1))


async def STM_alarm_status(slot):
    block = oidsSNMP()["slots_dict"][slot]
    check_alarm = []
    for i in range(1, oids()["blockOID"]['quantPort'][block] + 1):
        res = await snmp_get(oids()["main_alarm"]["alarmOID"][block] + f'.{slot}' + f'.{i}')
        check_alarm.append(str(res))

    return check_alarm


async def maskStmTIM():
    for block in oids()["main_alarm"]["maskSTMoid"]:
        for port in range(1, oids()["blockOID"]["quantPort"][block] + 1):
            await snmp_set(oids()['maskSTMoid'][block] + str(oidsSNMP()["slots_dict"][block]) + f'.{port}',
                           Integer(190))
