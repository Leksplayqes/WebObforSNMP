import random
import pytest
from MainConnectFunc import oids as get_oids
from MainConnectFunc import oidsSNMP as get_oids_snmp
from MainConnectFunc import oidsVIAVI as get_viavi_oids
from MainConnectFunc import find_KS, snmp_get, snmp_set, hex_to_bin
from unit_tests.SnmpV7Sync import clearprior, set_prior, del_prior, QL_up_down, extPortCr, extThreshQL, extPortQL, \
    extPortConf, extThreshAlarm, extSourceID, prior_status, set_E1_QL, STM1_ext_port, STM1_QL_level, SETS_create
from unit_tests.SnmpV7alarm import check_alarmPH, alarmplusmask
from Vivavi.ViaviControl import VIAVI_set_command, VIAVI_get_command
from unit_tests.sshV7 import get_ssh_value, bd_alarm_get
from TRAP_analyze.ParseTrapLog import parse_snmp_log, clear_trap_log, wait_trap
from unit_tests.SMD2_utils import *
import time
import asyncio

OIDS_SNMP = get_oids_snmp()
OIDS = get_oids()
OIDS_VIAVI = get_viavi_oids()
SLOTS_DICT = OIDS_SNMP.get("slots_dict", {})
KC_SLOT = find_KS()
''' 
Проверка создания и удаления приоритетов синхронизации для всех возможных блоков
Функция создает приоритет с указанным блоком, сверяет SNMP и регистры. 
Далее удаляет приоритет и проверяет, что регистры очистились
Добавлен анализ TRAP сообщений с изменением статуса приоритета синхронизации при создании/удалении источника синхр.
Добавлен анализ аварий SYNCv1PriorStatus в таблице hw_alarm
TASK #14382 
'''


@pytest.mark.parametrize('slot, priornum, portnum',
                         [(slot, priornum, portnum)
                          for slot in SLOTS_DICT
                          # if "E1" in SLOTS_DICT[slot] or "STM" in SLOTS_DICT[slot] or "KAD" in SLOTS_DICT[slot]
                          if "E1" in SLOTS_DICT[slot] or "STM" in SLOTS_DICT[slot]
                          for priornum in ['1', '2', '3', '4', '5', '6', '7']
                          for portnum in range(1, OIDS["blockOID"]["quantPort"][SLOTS_DICT[slot]] + 1)])
def test_STM_E1_create_del(slot, priornum, portnum):
    asyncio.run(clearprior())
    clear_trap_log()
    snmpSTM_set = str(asyncio.run(set_prior(slot, priornum, portnum)))
    time.sleep(0.5)
    regSTM_set = get_ssh_value(KC_SLOT, OIDS["priorityREG"][priornum])[:-1]
    expected_snmp = OIDS["blockOID"]["statusOID"][SLOTS_DICT[slot]] + slot + f'.{portnum}'
    assert snmpSTM_set == expected_snmp

    if SLOTS_DICT[slot] == "KAD":
        assert regSTM_set == KAD_reg_sync(portnum)
    elif "21E1" in SLOTS_DICT[slot]:
        assert regSTM_set == "0C0"
        assert E1_reg_sync(portnum) == get_ssh_value(slot, OIDS["syncOID"]["BUS_E1_reg"][priornum])[:-2] if int(
            slot) % 2 != 0 else get_ssh_value(slot, OIDS["syncOID"]["BUS_E1_reg"][priornum])[2:]
    elif "TE1" in SLOTS_DICT[slot]:
        assert regSTM_set == "0C0"
        ssh_value = OIDS["syncOID"]["BUS_E1_reg"][priornum] if int(portnum) < 5 else int(
            "8" + str(OIDS["syncOID"]["BUS_E1_reg"][priornum])[1:])
        assert E1_reg_sync(portnum) == get_ssh_value(slot, ssh_value)[:-2] if int(slot) % 2 == 0 else get_ssh_value(
            slot, ssh_value)[2:]
    elif "STM" in SLOTS_DICT[slot]:
        assert regSTM_set[1:] == STM_reg_sync(slot, portnum)

    # assert bd_alarm_get('SYNC_LOS', OIDS["syncOID"]["priorSTATUS"] + f"{priornum}")
    # trap_log = wait_trap(OIDS["syncOID"]["priorSTATUS"] + f"{priornum}", 2)
    # assert trap_log

    snmpSTM_del = asyncio.run(del_prior(priornum))
    tlntSTM_del = get_ssh_value(KC_SLOT, OIDS["priorityREG"][priornum])

    assert snmpSTM_del == OIDS["equipOID"]["portNull"] and tlntSTM_del == '0000'
    time.sleep(0.5)

    # assert not bd_alarm_get('SYNC_LOS', OIDS["syncOID"]["priorSTATUS"] + f"{priornum}")

    # trap_log = wait_trap(OIDS["syncOID"]["priorSTATUS"] + f"{priornum}", 3)
    # assert trap_log


'''Проверка включения режимов синхронизации (с/без анализа QL)'''


def test_QLmodeDOWN():
    snmpQL_set = asyncio.run(QL_up_down("down"))
    tlntQL_set = get_ssh_value(KC_SLOT, '3E')
    assert snmpQL_set == 0 and tlntQL_set == '0000'


def test_QLmodeUP():
    snmpQL_set = asyncio.run(QL_up_down("up"))
    tlntQL_set = get_ssh_value(KC_SLOT, '3E')
    assert snmpQL_set == 1 and tlntQL_set == '0001'


'''Проверка создания внешнего источника синхронизации'''


@pytest.mark.parametrize("priornum, portnum",
                         [(priornum, portnum)
                          for priornum in range(1, 9 if OIDS_SNMP["name"] != "SMD2v2" else 8)
                          for portnum in range(1, 3)])
def test_extPortID(priornum, portnum):
    asyncio.run(clearprior())
    exIDcr = asyncio.run(extPortCr(str(priornum), str(portnum)))
    asyncio.run(extPortQL(str(portnum), "0"))
    assert exIDcr == OIDS["syncOID"]["extTable"]["extID"] + str(portnum)
    reg_value = get_ssh_value(KC_SLOT, OIDS["priorityREG"][str(priornum)])
    expected_value = "0200" if str(portnum) == "1" else "0300"
    assert reg_value == expected_value

    exIDdel = asyncio.run(del_prior(str(priornum)))
    assert exIDdel == OIDS["equipOID"]["portNull"]

    reg_after_del = get_ssh_value(KC_SLOT, OIDS["priorityREG"][str(priornum)])
    assert reg_after_del == "0000"


'''Проверка установки качества на источнике внешней синхронизации'''


@pytest.mark.parametrize("priornum, portnum, value",
                         [(priornum, portnum, value)
                          for priornum in [str(x) for x in range(1, 9 if OIDS_SNMP["name"] != "SMD2v2" else 8)]
                          for portnum in range(1, 3)
                          for value in [2, 4, 8, 11, 15]])
def test_extPortQL(priornum, portnum, value):
    asyncio.run(clearprior())
    extCr = asyncio.run(extPortCr(priornum, str(portnum)))
    extQl = asyncio.run(extPortQL(str(portnum), value))

    assert extCr == OIDS["syncOID"]["extTable"]["extID"] + str(portnum)
    assert extQl == value

    reg_value = get_ssh_value(KC_SLOT, OIDS["priorityREG"][priornum])
    expected_prefix = "020" if str(portnum) == "1" else "030"
    expected_value = expected_prefix + f'{OIDS["qualDICT"][str(value)]}'
    assert reg_value == expected_value


'''Проверка установки режимов МГц и Мбит для портов вн. синхронизации'''


@pytest.mark.parametrize("portnum, value",
                         [(portnum, value)
                          for portnum in range(1, 3)
                          for value in range(0, 2)])
def test_extPortConf(portnum, value):
    extConf = asyncio.run(extPortConf(str(portnum), value))
    assert extConf == value
    reg_value = bin(int(get_ssh_value(KC_SLOT, '22'))).replace("b", "")
    assert reg_value[-int(portnum)] == str(value)


'''Проверка на использование портов STM в качестве источника для выхода портов внешней синхронизации'''


@pytest.mark.parametrize('slot, portnum, blockport',
                         [(slot, portnum, blockport)
                          for slot in SLOTS_DICT if "STM" in SLOTS_DICT[slot]
                          for portnum in range(1, 3)
                          for blockport in range(1, OIDS["blockOID"]["quantPort"][SLOTS_DICT[slot]] + 1)])
def test_extSourceID(slot, portnum, blockport):
    block = SLOTS_DICT[slot]
    extSrcID = asyncio.run(extSourceID(str(portnum), slot, str(blockport)))
    assert str(extSrcID) == OIDS["blockOID"]["statusOID"][block] + slot + f'.{blockport}'
    assert get_ssh_value(KC_SLOT, '24')[-(int(portnum))] == STM_extport_sync(slot, blockport)


@pytest.mark.parametrize("portnum", range(1, 3))
def test_EXT_category(portnum):
    for i in range(7):
        val = bytes([i])
        result = asyncio.run(snmp_set(OIDS["syncOID"]["extTable"]["extAlarmCategory"] + str(portnum), OctetString(val)))
        if i == 0 or i == 6:
            assert not result
        else:
            assert result


@pytest.mark.parametrize("priornum", [(priornum)
                                      for priornum in range(1, 8)])
def test_FDEV_enable(priornum):
    fdev_snmp_en = str(asyncio.run(snmp_set(OIDS["syncOID"]["fdevTable"]["FDEV_datchMODE_oid"] + str(priornum), Integer(5))))
    datch = get_ssh_value(KC_SLOT, OIDS["syncOID"]["fdevTable"]["FDEV_datchMODE_reg"])
    assert fdev_snmp_en == "5"
    assert hex_to_bin(datch)[-int(priornum)] == "1"


@pytest.mark.parametrize("priornum", [(priornum)
                                      for priornum in range(1, 8)])
def test_FDEV_disable(priornum):
    fdev_snmp_dis = str(asyncio.run(snmp_set(OIDS["syncOID"]["fdevTable"]["FDEV_datchMODE_oid"] + str(priornum), Integer(0))))
    datch = get_ssh_value(KC_SLOT, OIDS["syncOID"]["fdevTable"]["FDEV_datchMODE_reg"])
    assert fdev_snmp_dis == "0"
    assert hex_to_bin(datch)[-int(priornum)] == "0"


@pytest.mark.parametrize("priornum", [(priornum)
                                      for priornum in range(1, 8)])
def test_FDEV_category(priornum):
    for i in range(7):
        val = bytes([i])
        result = asyncio.run(snmp_set(OIDS["syncOID"]["fdevTable"]["FDEV_alarmCategory_oid"] + str(priornum), OctetString(val)))
        if i == 0 or i == 6:
            assert not result
        else:
            assert result


@pytest.mark.parametrize("portnum", range(1, 3))
@pytest.mark.parametrize("val", [0, 1])
def test_clock_ext(portnum, val):
    oid = OIDS["syncOID"]["extTable"]["extConf"] + str(portnum)
    reg_oid = OIDS["syncOID"]["extTable"]["extConf_reg"]

    assert str(asyncio.run(snmp_set(oid, Integer(val)))) == str(val)

    reg_bin = hex_to_bin(get_ssh_value(KC_SLOT, reg_oid))
    assert reg_bin[-portnum] == str(val)


'''Проверка на статус приоритета синхронизации, созданного с участием безаварийного порта'''


@pytest.mark.parametrize("slot, portnum, priornum",
                         [(int(w["dev_slot"]), int(w["dev_port"]), priornum)
                          for w in OIDS_VIAVI["wiring"]
                          if "STM" in w["dev_interface"]
                          for priornum in range(1, 9)
                          if str(asyncio.run(check_alarmPH(int(w["dev_slot"]), int(w["dev_port"])))) not in ["1", "2"]])
def test_prior_statusSTM(slot, portnum, priornum):
    numprior = {"1": -2, "2": -3, "3": -4, "4": -5, "5": -7, "6": -8, "7": -9, "8": -10} if OIDS_SNMP[
                                                                                                "name"] != "SMD2v2" else {
        "1": -1, "2": -2, "3": -3, "4": -4, "5": -5, "6": -6, "7": -7}
    slot = str(slot)
    asyncio.run(clearprior())
    # clear_trap_log()
    snmpSTM_set = asyncio.run(set_prior(slot, str(priornum), str(portnum)))
    time.sleep(80)

    prstatustlnt = get_ssh_value(KC_SLOT, '3A')
    assert asyncio.run(prior_status(priornum)) == 1
    assert bin(int(prstatustlnt, 16)).replace('b', '')[numprior[str(priornum)]] == '0'

    KCpriorAlarm = get_ssh_value(KC_SLOT, '3A')
    assert bin(int(KCpriorAlarm, 16)).replace('b', '')[numprior[str(priornum)]] == "0"
    assert str(asyncio.run(snmp_get(OIDS["syncOID"]["priorACTIVE"]))) == str(int(priornum) - 1)

    # trap_log = parse_snmp_log(OIDS["syncOID"]["priorSTATUS"] + f"{priornum}", 2)
    # assert OIDS["syncOID"]["priorSTATUS"] + f"{priornum}" == trap_log[0]
    # assert str(trap_log[1]) in ["1", "2"]

    tlntSTM_set = get_ssh_value(KC_SLOT,
                                OIDS["priorityREG"][str(priornum)])
    expected_snmp = OIDS["blockOID"]["statusOID"][SLOTS_DICT[slot]] + slot + f'.{portnum}'
    assert str(snmpSTM_set) == expected_snmp and tlntSTM_set != '0000'

    snmpSTM_del = asyncio.run(del_prior(str(priornum)))
    tlntSTM_del = get_ssh_value(KC_SLOT,
                                OIDS["priorityREG"][str(priornum)])
    assert snmpSTM_del == OIDS["equipOID"]["portNull"] and tlntSTM_del == '0000'


'''Проверка уровня качества на входе блоков СТМ'''


@pytest.mark.parametrize('slot, ql',
                         [(slot, ql)
                          for slot in SLOTS_DICT if 'STM' in SLOTS_DICT[slot]
                          for ql in OIDS["qualDICT"]])
def test_QLSTM_get(slot, ql):
    asyncio.run(clearprior())
    STM1alarm = list(asyncio.run(STM_alarm_status(slot)).values())

    for i in range(len(STM1alarm)):
        if int(STM1alarm[i]) == 0 or STM1alarm[i] == 64:
            VIAVI_set_command(SLOTS_DICT[slot], ":SOURCE:SDH:MS:Z1A:BYTE:VIEW", ql)

            reg_value = get_ssh_value(slot, OIDS['syncOID']['stmQLgetREG'][SLOTS_DICT[slot]][str(i + 1)])[-1]
            assert reg_value == OIDS["qualDICT"][ql]

            snmp_ql = asyncio.run(STM1_QL_level(slot, i + 1))
            assert OIDS["qualDICT"][str(snmp_ql)] == OIDS["qualDICT"][ql]


'''Проверка передачи качества ГСЭ по потокам STM'''


@pytest.mark.parametrize('slot, ql',
                         [(slot, ql)
                          for slot in SLOTS_DICT if 'STM' in SLOTS_DICT[slot]
                          for ql in OIDS["qualDICT"]])
def test_QLSTM_set(slot, ql):
    asyncio.run(clearprior())
    asyncio.run(SETS_create("1", int(ql)))
    STM1alarm = list(asyncio.run(STM_alarm_status(slot)).values())

    for i in range(len(STM1alarm)):
        if int(STM1alarm[i]) == 0 or int(STM1alarm[i]) == 64:
            time.sleep(30)

            reg_value = get_ssh_value(slot, OIDS["stmQLset"][SLOTS_DICT[slot]][str(i + 1)])
            assert OIDS["qualDICT"][str(ql)] in reg_value

            time.sleep(1)
            resQLstm = VIAVI_get_command(SLOTS_DICT[slot],
                                         ":SENSE:DATA? INTEGER:SONET:LINE:S1:SYNC:STATUS")[2:-2]
            expected_ql = oidsVIAVI()["reqSTMql"][resQLstm]
            assert expected_ql == get_ssh_value(slot, OIDS["stmQLset"][SLOTS_DICT[slot]][str(i + 1)])


'''Проверка установки уровней QL для интерфейсов E1'''


@pytest.mark.parametrize('slot, priornum, portnum',
                         [(slot, priornum, portnum)
                          for slot in SLOTS_DICT if 'E1' in SLOTS_DICT[slot]
                          for priornum in [str(x) for x in range(1, 9)]
                          for portnum in range(1, OIDS["blockOID"]["quantPort"][SLOTS_DICT[slot]])])
def test_QLE1_set(slot, priornum, portnum):
    asyncio.run(clearprior())
    asyncio.run(set_prior(slot, priornum, portnum))
    assert get_ssh_value(find_KS(), OIDS["priorityREG"][str(priornum)]) != "0000"

    for value in OIDS["qualDICT"]:
        asyncio.run(set_E1_QL(slot, portnum, int(value)))
        tlntE1QL = get_ssh_value(find_KS(), OIDS["priorityREG"][str(priornum)])[-1]
        assert tlntE1QL == OIDS["qualDICT"][value]


'''Проверка записи блоков СТМ как источников выходного сигнала'''


@pytest.mark.parametrize('extport, portnum, slot',
                         [(extport, portnum, slot)
                          for slot in SLOTS_DICT if "STM" in SLOTS_DICT[slot]
                          for extport in range(1, 3)
                          for portnum in range(1, OIDS["blockOID"]["quantPort"][SLOTS_DICT[slot]] + 1)])
def test_STM_extport(extport, portnum, slot):
    extportvalue = asyncio.run(STM1_ext_port(extport, portnum, slot))

    assert extportvalue == OIDS["blockOID"]["statusOID"][SLOTS_DICT[slot]] + slot + f'.{portnum}'
    if OIDS_SNMP["name"] != "SMD2v2":
        assert bin(int(get_ssh_value(find_KS(), '24')))[-int(extport)] == "1"
        STMextport = get_ssh_value(slot, OIDS["extSourceSTM"][SLOTS_DICT[slot]])
        assert OIDS["syncOID"]["prior_dict"][STMextport[-extport]] == str(portnum)
    else:
        assert get_ssh_value(find_KS(), '24')[-int(extport)] == str(portnum) if slot == "17" else str(
            4 + int(portnum))


'''Проверка соответствия текущего уровня качества источника синхронизации на входе блоков СТМ с качеством, записанным в КС'''


@pytest.mark.parametrize('slot, extport, portnum',
                         [(slot, extport, portnum)
                          for slot in SLOTS_DICT if 'STM' in SLOTS_DICT[slot]
                          for extport in range(1, 3)
                          for portnum in range(1, OIDS["blockOID"]["quantPort"][SLOTS_DICT[slot]] + 1)])
def test_STM_QL_extport(slot, extport, portnum):
    asyncio.run(STM1_ext_port(extport, portnum, slot))
    extQLKS = get_ssh_value(find_KS(), OIDS["syncOID"]["KCqlGETreg"][str(extport)])
    extQLstm = get_ssh_value(slot, OIDS['syncOID']['stmQLgetREG'][SLOTS_DICT[slot]][str(portnum)])
    assert extQLKS == extQLstm


'''Проверка аварий по порогам статистики для каждого интерфейсного блока и каждого качества на приеме'''


@pytest.mark.parametrize('slot, extPort, portnum, priornum',
                         [(slot, extPort, portnum, priornum)
                          for slot in SLOTS_DICT if 'STM' in SLOTS_DICT[slot]
                          for extPort in range(1, 3)
                          for portnum in range(1, OIDS["blockOID"]["quantPort"][SLOTS_DICT[slot]])
                          for priornum in [str(x) for x in range(1, 8)]])
def test_ThresQL_AlarmBlock(slot, extPort, portnum, priornum):
    asyncio.run(clearprior())
    STM1alarm = list(asyncio.run(STM_alarm_status(slot)).values())
    stmql_values = []
    for i in range(len(STM1alarm)):
        if STM1alarm[i] == "0":
            asyncio.run(set_prior(slot, priornum, str(i + 1)))
            asyncio.run(extSourceID(str(extPort), slot, str(i + 1)))
            stmql_values.append(asyncio.run(STM1_QL_level(slot, i + 1)))

            for QL in OIDS["qualDICT"]:
                if QL != "0" and QL != "15" and stmql_values:
                    ThreshQL = asyncio.run(extThreshQL(str(extPort), int(QL)))

                    if ThreshQL >= stmql_values[0] != 0 and stmql_values[0] != 15:
                        time.sleep(1)
                        QLalarmdatch = asyncio.run(extThreshAlarm(str(extPort)))
                        assert QLalarmdatch == 0
                        assert bin(int(get_ssh_value(find_KS(), "4e")))[-int(extPort)] in ["0", "b"]
                    else:
                        time.sleep(1)
                        assert asyncio.run(extThreshAlarm(str(extPort))) == 2
                        assert bin(int(get_ssh_value(find_KS(), "4e")))[-int(extPort)] == "1"


'''Проверка аварии по порогам с выбранным ГСЭ, как источник вн синхронизации'''


@pytest.mark.parametrize('portnum, thresh_quality, sets_quality',
                         [(portnum, thresh_quality, sets_quality)
                          for portnum in range(1, 3)
                          for thresh_quality in [2, 4, 8, 11]
                          for sets_quality in [2]])
def test_ThreshQL_AlarmSETS(portnum, thresh_quality, sets_quality):
    asyncio.run(QL_up_down("up"))
    asyncio.run(clearprior())

    asyncio.run(SETS_create(str(random.randint(1, 8)), sets_quality))
    asyncio.run(extSourceID(str(portnum), "SETS", ''))
    asyncio.run(extThreshQL(str(portnum), 11))
    time.sleep(70)

    clear_trap_log()
    asyncio.run(extThreshQL(str(portnum), thresh_quality))

    tlnextThreshQL = get_ssh_value(KC_SLOT, "4a") if portnum == 1 else get_ssh_value(KC_SLOT, "4c")
    assert int(tlnextThreshQL, 16) == thresh_quality

    if thresh_quality >= sets_quality and sets_quality not in [0, 15]:
        assert int(asyncio.run(extThreshAlarm(str(portnum)))) == 0
        assert bin(int(get_ssh_value(KC_SLOT, "4e")))[-portnum] in ["0", "b"]
    elif sets_quality in [0, 15]:
        assert int(asyncio.run(extThreshAlarm(str(portnum)))) == 2
        # assert bd_alarm_get('LOW_QL', OIDS["syncOID"]["extTable"]["extThreshAlarm"] + str(portnum))
        assert bin(int(get_ssh_value(KC_SLOT, "4e")))[-portnum] == "1"
    else:
        assert int(asyncio.run(extThreshAlarm(str(portnum)))) == 2
        # assert bd_alarm_get('LOW_QL', OIDS["syncOID"]["extTable"]["extThreshAlarm"] + str(portnum))

        # trap_log = parse_snmp_log(OIDS["syncOID"]["extTable"]["extThreshAlarm"] + str(portnum), 2)
        # assert OIDS["syncOID"]["extTable"]["extThreshAlarm"] + str(portnum) == trap_log[0]
        # assert str(trap_log[1]) in ["1", "2"]

        assert bin(int(get_ssh_value(KC_SLOT, "4e")))[-portnum] == "1"
