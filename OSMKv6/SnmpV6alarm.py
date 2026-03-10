import asyncio
import json
import time

from puresnmp import Client, V2C, PyWrapper, ObjectIdentifier
from puresnmp.types import Integer, OctetString


def oids():
    with open("../OIDstatusNEW.json", "r") as jsonoid:
        oid = json.load(jsonoid)
    return oid["OSMKv6"]


async def typeOfEq():
    equipment = await client().get("1.3.6.1.2.1.1.1.0")
    return equipment


def client():
    return PyWrapper(Client(oids()["ipaddr"], V2C("private")))


def clientget():
    return PyWrapper(Client(oids()["ipaddr"], V2C("public")))


def check_loopback():
    for key in oids()["slots_dict"]:
        if oids()["slots_dict"][key] == oids()["loopback"][0]:
            return [key, oids()["loopback"][1]]


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


async def alarmplusmask(blocks: list):
    for block in blocks:
        for i in range(1, oids()["blockOID"]["quantPort"][block] + 1):
            await client().set(oids()['alarmMODE'][block] + str(oids()["slots_dict"][block]) + f'.{i}', Integer(2))
    await client().set(oids()['alarmMODE'][check_loopback()[0]] + str(
        oids()["slots_dict"][check_loopback()[0]]) + f'.{check_loopback()[1]}', Integer(0))


async def alarmplusmaslcnctSTM(blocks: list):
    for block in blocks:
        if "STM" in block:
            for port in range(1, oids()["blockOID"]["quantPort"][block] + 1):
                for vc in range(1, int(block[4:]) + 1):
                    await client().set(oids()['main_alarm']["alarmMODEcnct"][block] + str(oids()["slots_dict"][block]) + f'.{port}' + f'.{vc}',
                                       Integer(2))
        else:
            for k in range(1, 4):
                for l in range(1, 8):
                    await client().set(oids()['main_alarm']["alarmMODEcnct"][block] + str(
                        oids()["slots_dict"][block]) + f'.1.1' + f'.{k}' + f'.{l}' + f'.1',
                                       Integer(2))


async def check_alarmPH(block, portnum):
    alarm = await clientget().get(
        f'{oids()["main_alarm"]["alarm_status"]["physical"][block] + str(oids()["slots_dict"][block]) + f".{portnum}"}')
    return alarm


async def check_alarm_cnct(block, portnum, vc):
    alarm = await clientget().get(
        f'{oids()["main_alarm"]["alarm_status"]["connective"][block] + str(oids()["slots_dict"][block]) + f".{portnum}" + f".{vc}"}')
    return alarm


async def check_alarm_cnctE1(block, vc):
    alarm = await clientget().get(
        f'{oids()["main_alarm"]["alarm_status"]["connective"][block] + str(oids()["slots_dict"][block]) + f".1.1" + f".{klm_numbersE1(vc)}"}')
    return alarm


async def change_traceTD(block, portnum, value):
    traceTD = await client().set(
        f"{oids()['main_alarm']['alarm_setup_oid']['TIM']['TD'][block] + str(oids()['slots_dict'][block]) + f'.{portnum}'}",
        OctetString(f"{value}"))
    return traceTD


async def create_commutationVC4(block, port, vc):
    await client().set(
        f"{oids()['switch']['switch_portVC4'][check_loopback()[0]] + str(oids()['slots_dict'][check_loopback()[0]]) + '.' + str(oids()['loopback'][1]) + '.1'}",
        ObjectIdentifier(f"{oids()['switch']['data_directionVC4'][block] + str(oids()['slots_dict'][block]) + f'.{port}' + f'.{vc}'}"))
    await client().set(f"{oids()['switch']['switch_portVC4'][block] + str(oids()['slots_dict'][block]) + f'.{port}' + f'.{vc}'}", ObjectIdentifier(
        f"{oids()['switch']['data_directionVC4'][check_loopback()[0]] + str(oids()['slots_dict'][check_loopback()[0]]) + '.' + str(oids()['loopback'][1]) + '.1'}"))


async def create_commutationVC12(block, port, vc4, vc12):
    await client().set(
        f"{oids()['switch']['switch_portVC12'][check_loopback()[0]] + str(oids()['slots_dict'][check_loopback()[0]]) + '.' + str(oids()['loopback'][1]) + '.1.1.1.1'}",
        ObjectIdentifier(
            f"{oids()['switch']['data_directionVC12'][block] + str(oids()['slots_dict'][block]) + f'.{port}' + f'.{vc4}' + f'.{klm_numbers(vc12)}'}"))
    await client().set(
        f"{oids()['switch']['switch_portVC12'][block] + str(oids()['slots_dict'][block]) + f'.{port}' + f'.{vc4}' + f'.{klm_numbers(vc12)}'}",
        ObjectIdentifier(
            f"{oids()['switch']['data_directionVC12'][check_loopback()[0]] + str(oids()['slots_dict'][check_loopback()[0]]) + '.' + str(oids()['loopback'][1]) + '.1.1.1.1'}"))


async def portViavi():
    block = oids()["VIAVIcontrol"]["settings"]["NumOne"]["typeofport"]["Port1"]
    port = [portnum for portnum in range(1, oids()["blockOID"]["quantPort"][block] + 1) if
            [oids()["slots_dict"][block], str(portnum)] != oids()["loopback"] and
            await check_alarmPH(block, portnum) == 0 or
            await check_alarmPH(block, portnum) == 64]
    return [block, port[0]]


async def create_commutationE1(block, vc12):
    slot, port = await portViavi()
    await client().set(
        f"{oids()['switch']['switch_portVC12'][block] + str(oids()['slots_dict'][block]) + '.1.1.' + f'{klm_numbersE1(vc12)}'}",
        ObjectIdentifier(
            f"{oids()['switch']['data_directionVC12'][slot] + str(oids()['slots_dict'][slot]) + f'.{port}' + '.1.1.1.1'}"))
    await client().set(
        f"{oids()['switch']['switch_portVC12'][slot] + str(oids()['slots_dict'][slot]) + f'.{port}' + '.1.1.1.1'}",
        ObjectIdentifier(
            f"{oids()['switch']['data_directionVC12'][block] + str(oids()['slots_dict'][block]) + '.1.1.' + f'{klm_numbersE1(vc12)}'}"))


async def delete_commutation():
    await client().set("1.3.6.1.4.1.5756.3.3.1.1.5.2.0", Integer(1))


async def STM_alarm_status(blck):
    check_alarm = []
    for i in range(1, oids()["blockOID"]['quantPort'][blck] + 1):
        res = await clientget().get(oids()["alarmOID"][blck] + oids()["slots_dict"][blck] + f'.{i}')
        check_alarm.append(res)
    return check_alarm


async def maskStmTIM():
    for block in oids()["main_alarm"]["maskSTMoid"]:
        for port in range(1, oids()["blockOID"]["quantPort"][block] + 1):
            await client().set(oids()['maskSTMoid'][block] + str(oids()["slots_dict"][block]) + f'.{port}',
                               Integer(190))


async def otn():
    for i in range(1, 10000000):
        for port in range(1, 17):
            for value in range(0, 7):
                try:
                    await client().set(f"1.3.6.1.4.1.5756.9.1.2.10.1.2.1.2.1.6.3.{port}", Integer(value))
                    time.sleep(1)
                except:
                    print(Exception)
