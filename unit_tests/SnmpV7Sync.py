import asyncio

from MainConnectFunc import *
from pysnmp.hlapi.asyncio import ObjectIdentifier, Integer


async def typeOfEq():
    equipment = await snmp_get("1.3.6.1.4.1.5756.1.220.1.1.3")
    return equipment


async def clearprior():
    await snmp_set_bulk([
        (oids()["syncOID"]["priorID"] + str(port), ObjectIdentifier(oids()["equipOID"]["portNull"]))
        for port in range(1, 9 if oidsSNMP()["name"] != "SMD2v2" else 8)])


async def set_prior(slot, priornum, portnum):
    syncSTMset = await snmp_set(f'{oids()["syncOID"]["priorID"] + priornum}',
                                ObjectIdentifier(
                                    '.' + oids()["blockOID"]['statusOID'][oidsSNMP()["slots_dict"][slot]] + str(
                                        slot) + f'.{portnum}'))
    return syncSTMset


async def get_prior(priornum):
    STMget = await snmp_get(f'{oids()["syncOID"]["priorID"] + str(priornum)}')
    return STMget


async def del_prior(priornum):
    syncSTMdel = await snmp_set(f'{oids()["syncOID"]["priorID"] + priornum}',
                                ObjectIdentifier(oids()["equipOID"]['portNull']))
    return str(syncSTMdel)


async def QL_up_down(mode):
    if mode == "up":
        upQL = await  snmp_set(oids()["syncOID"]["modeQL"], Integer(1))
    else:
        upQL = await  snmp_set(oids()["syncOID"]["modeQL"], Integer(0))
    return upQL


async def STM_alarm_status(slot) -> dict:
    check_alarm = await snmp_getBulk(oids()["main_alarm"]["alarmOID"][oidsSNMP()['slots_dict'][slot]],
                                     oids()["blockOID"]['quantPort'][oidsSNMP()['slots_dict'][slot]])
    return check_alarm


async def prior_status(priornum):
    check_prior_status = await snmp_get(oids()["syncOID"]["priorSTATUS"] + str(priornum))
    return check_prior_status


async def STM1_QL_level(slot, portnum):
    QL_check = await snmp_get(oids()["syncOID"]["stmQLget"][oidsSNMP()['slots_dict'][slot]] + str(slot) + f'.{portnum}')
    return QL_check

async def SETS_create(portnum, value):
    SETS_value = await snmp_set(oids()['syncOID']["priorID"] + str(portnum),
                                ObjectIdentifier(oids()["syncOID"]["setsID"]))
    await snmp_set(oids()["syncOID"]["setsQL"], Integer(value))
    return SETS_value


async def SETS_QL():
    SETSQL = await snmp_get(oids()["syncOID"]["setsQL"])
    return SETSQL


async def STM1_ext_port(lgc,  slot, portnum):
    ext_port_set = await snmp_set(oids()["syncOID"]["extTable"]["extSourceID"] + str(lgc),
                                  ObjectIdentifier(
                                      oids()["blockOID"]["statusOID"][
                                          oidsSNMP()['slots_dict'][slot]] + slot + f'.{portnum}'))
    return str(ext_port_set)


async def extPortCr(priornum, portnum):
    extID = await snmp_set(oids()["syncOID"]["priorID"] + priornum,
                           ObjectIdentifier(oids()["syncOID"]["extTable"]["extID"] + portnum))
    return str(extID)


async def extPortQL(portnum, value):
    extQL = await snmp_set(oids()["syncOID"]["extTable"]["extSetQL"] + portnum, Integer(value))
    return int(extQL)


async def extSourceID(portnum, slot, blockport):
    if slot != 'SETS':
        sourceID = await snmp_set(oids()["syncOID"]["extTable"]["extSourceID"] + str(portnum), ObjectIdentifier(
            oids()["blockOID"]["statusOID"][oidsSNMP()['slots_dict'][slot]] + slot + f'.{blockport}'))
    else:
        sourceID = await snmp_set(oids()["syncOID"]["extTable"]["extSourceID"] + str(portnum), ObjectIdentifier(
            oids()["blockOID"]["statusOID"][slot]))
    return sourceID


async def extPortConf(portnum, value):
    extConf = await snmp_set(oids()["syncOID"]["extTable"]["extConf"] + portnum, Integer(value))
    return extConf


async def extThreshQL(portnum, value):
    extThresh = await snmp_set(oids()["syncOID"]["extTable"]["extThreshQL"] + str(portnum), Integer(value))
    return extThresh


async def extThreshAlarm(portnum):
    extThreshAl = await snmp_get(oids()["syncOID"]["extTable"]["extThreshAlarm"] + str(portnum))
    return extThreshAl

async def STMcreateWorkPrior(slot, priornum):
    STMalarm = await STM_alarm_status(slot)
    for i in range(len(STMalarm)):
        if STMalarm[i] == 0:
            await set_prior(slot, priornum, str(i + 1))


async def curPrior():
    activePrior = await clientget().get(oids()["syncOID"]["priorACTIVE"])
    return activePrior + 1


async def get_multi_prior():
    STMget = await snmp_getBulk(f'{oids()["syncOID"]["priorID"] + "1"}', 8)
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


async def set_E1_QL(slot, portnum, value):
    E1_set = await snmp_set(oids()["E1QLset"][oidsSNMP()["slots_dict"][slot]] + slot + f'.{portnum}', Integer(value))
    return E1_set


async def get_priorID(nums):
    prID = await clientget().get(f'{oids()["syncOID"]["priorID"]}{nums}')
    for block in oids()["statusOID"]:
        if oids()["statusOID"][block] in prID:
            return block


async def createPrbyID(prior, oid):
    prSet = await snmp_set(oids()["syncOID"]["priorID"] + prior, ObjectIdentifier(oid))
    return prSet


async def maskStmTIM():
    for block in oids()["slots_dict"]:
        if "STM" in block:
            for port in range(1, oids()["blockOID"]["quantPort"][block] + 1):
                await snmp_set(oids()['maskSTMoid'][block] + str(oids()["slots_dict"][block]) + f'.{port}',
                               Integer(190))


async def UNmaskStmTIM():
    for block in oids()["slots_dict"]:
        if "STM" in block:
            for port in range(1, oids()["blockOID"]["quantPort"][block] + 1):
                await snmp_set(oids()['maskSTMoid'][block] + str(oids()["slots_dict"][block]) + f'.{port}',
                               Integer(254))


async def syncSTMenable(slot, port):
    await snmp_set(oids()["syncOID"]["syncSTMenable"][oidsSNMP()["slots_dict"][str(slot)]] + str(slot) + f".{port}", Integer(1))


async def setsQL(ql):
    await snmp_set(oids()["syncOID"]["setsQL"], Integer(ql))

