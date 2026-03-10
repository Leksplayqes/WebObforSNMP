import asyncio
import json

from puresnmp import Client, V2C, PyWrapper, ObjectIdentifier
from puresnmp.types import Integer


def oids():
    with open("../OIDstatusNEW.json", "r") as jsonoid:
        oid = json.load(jsonoid)
    return oid["OSMKv6"]


async def typeOfEq():
    equipment = await client().get("1.3.6.1.2.1.1.1.0")
    return equipment
def client_byIP(ip):
    return PyWrapper(Client(ip, V2C("public")))

def client():
    return PyWrapper(Client(oids()["ipaddr"], V2C("private")))


def clientget():
    return PyWrapper(Client(oids()["ipaddr"], V2C("public")))


def checkpriorregID(block, portnum):
    if oids()["slots_dict"][block] == "17":
        nums = {1: "4", 2: "5", 3: "6", 4: "7"}
        portindexreg = nums[portnum]
    elif oids()["slots_dict"][block] == "18":
        nums = {1: "8", 2: "9", 3: "a", 4: "b"}
        portindexreg = nums[portnum]
    else:
        portindexreg = "c"
    return portindexreg


async def alarmplusmask(blocks):
    for block in blocks:
        for i in range(1, oids()["blockOID"]["quantPort"][block] + 1):
            await client().set(oids()['main_alarm']['alarmMODE'][block] + str(oids()["slots_dict"][block]) + f'.{i}', Integer(2))


async def clearprior():
    for i in range(1, 9):
        await client().set(f'{oids()["syncOID"]["priorID"]}{i}', ObjectIdentifier(oids()["equipOID"]["portNull"]))


async def set_prior(block, priornum, portnum):
    syncSTMset = await client().set(f'{oids()["syncOID"]["priorID"] + priornum}',
                                    ObjectIdentifier(
                                        '.' + oids()["blockOID"]['statusOID'][block] + oids()["slots_dict"][block] + f'.{portnum}'))
    return syncSTMset

async def get_prior(priornum):
    STMget = await clientget().get(f'{oids()["syncOID"]["priorID"] + priornum}')
    return STMget


async def del_prior(priornum):
    syncSTMdel = await client().set(f'{oids()["syncOID"]["priorID"] + priornum}', ObjectIdentifier(oids()['portNull']))
    return syncSTMdel


async def QL_up_down(mode):
    if mode == "up":
        upQL = await  client().set(oids()["syncOID"]["modeQL"], Integer(1))
    else:
        upQL = await  client().set(oids()["syncOID"]["modeQL"], Integer(0))
    return upQL


async def STM_alarm_status(blck):
    check_alarm = []
    for i in range(1, oids()["blockOID"]['quantPort'][blck] + 1):
        res = await clientget().get(oids()["alarmOID"][blck] + oids()["slots_dict"][blck] + f'.{i}')
        check_alarm.append(res)
    return check_alarm


async def prior_status(priornum):
    check_prior_status = await clientget().get(oids()["syncOID"]["priorSTATUS"] + str(priornum))
    return check_prior_status


async def STM1_QL_level(block, portnum):
    QL_check = await clientget().get(oids()["stmQLget"][block] + oids()["slots_dict"][block] + f'.{portnum}')
    return QL_check


async def SETS_create(portnum, value):
    SETS_value = await client().set(oids()['syncOID']["priorID"] + str(portnum),
                                    ObjectIdentifier(oids()["syncOID"]["setsID"]))
    await client().set(oids()["syncOID"]["setsQL"], Integer(value))
    return SETS_value


async def SETS_QL():
    SETSQL = await clientget().get(oids()["syncOID"]["setsQL"])
    return SETSQL


async def STM1_ext_port(lgc, portnum, block):
    ext_port_set = await client().set(oids()["syncOID"]["extTable"]["extSourceID"] + str(lgc),
                                      ObjectIdentifier(
                                          oids()["statusOID"][block] + oids()["slots_dict"][block] + f'.{portnum}'))
    return ext_port_set


async def extPortCr(priornum, portnum):
    extID = await client().set(oids()["syncOID"]["priorID"] + priornum,
                               ObjectIdentifier(oids()["syncOID"]["extTable"]["extID"] + portnum))
    return extID


async def extPortQL(portnum, value):
    extQL = await client().set(oids()["syncOID"]["extTable"]["extSetQL"] + portnum, Integer(value))
    return extQL


async def extSourceID(portnum, block, blockport):
    if block == "SETS":
        sourceID = await client().set(oids()["syncOID"]["extTable"]["extSourceID"] + str(portnum),
                                      ObjectIdentifier(oids()["syncOID"]["setsID"]))
    else:
        sourceID = await client().set(oids()["syncOID"]["extTable"]["extSourceID"] + str(portnum), ObjectIdentifier(
            oids()["statusOID"][block] + oids()["slots_dict"][block] + f'.{blockport}'))
    
    return sourceID


async def extPortConf(portnum, value):
    extConf = await client().set(oids()["syncOID"]["extTable"]["extConf"] + portnum, Integer(value))
    return extConf


async def extThreshQL(portnum, value):
    extThresh = await client().set(oids()["syncOID"]["extTable"]["extThreshQL"] + str(portnum), Integer(value))
    return extThresh


async def extThreshAlarm(portnum):
    extThreshAl = await clientget().get(oids()["syncOID"]["extTable"]["extThreshAlarm"] + str(portnum))
    return extThreshAl


def STMcreateWorkPrior(block, priornum):
    STMalarm = asyncio.run(STM_alarm_status(block))
    for i in range(len(STMalarm)):
        if STMalarm[i] == 0:
            asyncio.run(set_prior(block, priornum, str(i + 1)))


async def curPrior():
    activePrior = await clientget().get(oids()["syncOID"]["priorACTIVE"])
    return activePrior + 1


async def get_multi_prior():
    STMget = await clientget().multiget(
        [(f'{oids()["syncOID"]["priorID"] + "1"}'), (f'{oids()["syncOID"]["priorID"] + "2"}'),
         (f'{oids()["syncOID"]["priorID"] + "3"}'),
         (f'{oids()["syncOID"]["priorID"] + "4"}'), (f'{oids()["syncOID"]["priorID"] + "5"}'),
         (f'{oids()["syncOID"]["priorID"] + "6"}'),
         (f'{oids()["syncOID"]["priorID"] + "7"}')])
    return STMget


async def get_multi_slotID():
    listofprior = []
    fullTable = await clientget().multiget(
        [(f'{oids()["syncOID"]["priorID"] + "1"}'), (f'{oids()["syncOID"]["priorID"] + "2"}'),
         (f'{oids()["syncOID"]["priorID"] + "3"}'),
         (f'{oids()["syncOID"]["priorID"] + "4"}'), (f'{oids()["syncOID"]["priorID"] + "5"}'),
         (f'{oids()["syncOID"]["priorID"] + "6"}'),
         (f'{oids()["syncOID"]["priorID"] + "7"}')])
    for i in fullTable:
        if i != '1.3.6.1.4.1.5756.1.205.0':
            for block in oids()["statusOID"]:
                if oids()["statusOID"][block] in i:
                    listofprior.append(block)
    return listofprior


async def set_E1_QL(block, portnum, value):
    E1_set = await client().set(oids()["E1QLset"][block] + oids()["slots_dict"][block] + f'.{portnum}', Integer(value))
    return E1_set


async def get_priorID(nums):
    prID = await clientget().get(f'{oids()["syncOID"]["priorID"]}{nums}')
    for block in oids()["statusOID"]:
        if oids()["statusOID"][block] in prID:
            return block


async def createPrbyID(prior, oid):
    prSet = await client().set(oids()["syncOID"]["priorID"] + prior, ObjectIdentifier(oid))
    return prSet


async def maskStmTIM():
    for block in oids()["slots_dict"]:
        if "STM" in block:
            for port in range(1, oids()["blockOID"]["quantPort"][block] + 1):
                await client().set(oids()['maskSTMoid'][block] + str(oids()["slots_dict"][block]) + f'.{port}',
                                   Integer(190))


async def UNmaskStmTIM():
    for block in oids()["slots_dict"]:
        if "STM" in block:
            for port in range(1, oids()["blockOID"]["quantPort"][block] + 1):
                await client().set(oids()['maskSTMoid'][block] + str(oids()["slots_dict"][block]) + f'.{port}',
                                   Integer(254))
