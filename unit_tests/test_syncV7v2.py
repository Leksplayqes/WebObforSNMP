import random
import pytest
from MainConnectFunc import oids as get_oids
from MainConnectFunc import oidsSNMP as get_oids_snmp
from MainConnectFunc import oidsVIAVI as get_viavi_oids
from MainConnectFunc import find_KS, snmp_get, snmp_set
from unit_tests.SnmpV7Sync import clearprior, set_prior, del_prior, QL_up_down, extPortCr, extThreshQL, extPortQL, \
    extPortConf, extThreshAlarm, extSourceID, prior_status, set_E1_QL, STM1_ext_port, STM1_QL_level, SETS_create, \
    STM_alarm_status, syncSTMenable, setsQL
from unit_tests.SnmpV7alarm import check_alarmPH, alarmplusmask
from Vivavi.ViaviControl import VIAVI_set_command, VIAVI_get_command
from unit_tests.sshV7 import get_ssh_value, bd_alarm_get
from TRAP_analyze.ParseTrapLog import parse_snmp_log, clear_trap_log, wait_trap

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


@pytest.fixture(scope="module")
def clear_createSETS():
    asyncio.run(clearprior())
    asyncio.run(SETS_create("1", 11))
    time.sleep(35)


@pytest.mark.parametrize('slot, priornum, portnum',
                         [(slot, priornum, portnum)
                          for slot, val in SLOTS_DICT.items()
                          if str(slot) in OIDS_SNMP.get("active_slots", {}) and ("E1" in val or "STM" in val)
                          for priornum in
                          ['1', '2', '3', '4', '5', '6', '7', '8']
                          for portnum in range(1, OIDS["blockOID"]["quantPort"][SLOTS_DICT[slot]] + 1)])
def test_STM_E1_create_del(slot, priornum, portnum):
    asyncio.run(clearprior())
    clear_trap_log()
    snmpSTM_set = str(asyncio.run(set_prior(slot, priornum, portnum)))
    time.sleep(2)

    regSTM_set = get_ssh_value(KC_SLOT, OIDS["priorityREG"][priornum])

    expected_snmp = OIDS["blockOID"]["statusOID"][SLOTS_DICT[slot]] + slot + f'.{portnum}'
    assert snmpSTM_set == expected_snmp and regSTM_set[:2] != '0000'
    assert bd_alarm_get('SYNC_LOS', OIDS["syncOID"]["priorSTATUS"] + f"{priornum}")
    trap_log = wait_trap(OIDS["syncOID"]["priorSTATUS"] + f"{priornum}", 2)
    assert trap_log

    snmpSTM_del = str(asyncio.run(del_prior(priornum)))
    tlntSTM_del = get_ssh_value(KC_SLOT, OIDS["priorityREG"][priornum])

    if "9" in SLOTS_DICT and "10" in SLOTS_DICT:
        tlntSTM_del2 = get_ssh_value("10", OIDS["priorityREG"][priornum])
        assert tlntSTM_del == tlntSTM_del2

    assert snmpSTM_del == OIDS["equipOID"]["portNull"] and tlntSTM_del == '0000'
    time.sleep(2)

    assert not bd_alarm_get('SYNC_LOS', OIDS["syncOID"]["priorSTATUS"] + f"{priornum}")

    trap_log = wait_trap(OIDS["syncOID"]["priorSTATUS"] + f"{priornum}", 3)
    assert trap_log


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
                          for priornum in range(1, 9)
                          for portnum in range(1, 3)])
def test_extPortID(priornum, portnum):
    asyncio.run(clearprior())
    exIDcr = asyncio.run(extPortCr(str(priornum), str(portnum)))

    assert exIDcr == OIDS["syncOID"]["extTable"]["extID"] + str(portnum)
    reg_value = get_ssh_value(KC_SLOT, OIDS["priorityREG"][str(priornum)])
    expected_value = "0200" if str(portnum) == "1" else "0300"
    assert reg_value == expected_value

    exIDdel = asyncio.run(del_prior(str(priornum)))
    assert exIDdel == OIDS["equipOID"]["portNull"]

    reg_after_del = get_ssh_value(KC_SLOT, OIDS["priorityREG"][str(priornum)])
    assert reg_after_del == "0000"


'''Проверка занятия и очистки шины, при создании и удалении приоритета синхронизации'''



@pytest.mark.parametrize("slot, portnum, priornum",
                         [(slot, portnum, priornum)
                          for slot, val in SLOTS_DICT.items()
                          if str(slot) in OIDS_SNMP.get("active_slots", {}) and ("E1" in val or "STM" in val)
                          for priornum in ['1', '2', '3', '4', '5', '6', '7', '8']
                          for portnum in range(1, OIDS["blockOID"]["quantPort"][SLOTS_DICT[slot]] + 1)])
def test_busSYNC(slot, priornum, portnum):
    dictPort = {"1": "1", "3": "2", "5": "3", "7": "4", "9": "5", "B": "6", "D": "7", "F": "8", }
    asyncio.run(clearprior())
    asyncio.run(set_prior(slot, str(priornum), str(portnum)))
    if SLOTS_DICT[slot] != "63E1M":
        busSTM = get_ssh_value(slot, OIDS["syncOID"]["busSYNCsource"][SLOTS_DICT[slot]][priornum])
        busSTM = busSTM * 3
        assert int(dictPort[busSTM[-int(priornum)]]) == int(portnum)
        asyncio.run(del_prior(priornum))
        assert get_ssh_value(slot, OIDS["syncOID"]["busSYNCsource"][SLOTS_DICT[slot]][priornum]) == "0000"
    else:
        if int(portnum) < 22:
            TUG = 1
        elif 21 < int(portnum) < 43:
            TUG = 2
            portnum = int(portnum) - 21
        else:
            TUG = 3
            portnum = int(portnum) - 42
        busSTM = get_ssh_value(slot, OIDS["syncOID"]["busSYNCsource"][SLOTS_DICT[slot]][f'{priornum}.{TUG}'])
        if int(priornum) % 2 != 0:
            busSTM = busSTM[-2:]
        else:
            busSTM = busSTM[:-2]
        busSTM = int(busSTM, 16)
        assert int(busSTM) == int(portnum)
        asyncio.run(del_prior(priornum))
        assert get_ssh_value(slot, OIDS["syncOID"]["busSYNCsource"][SLOTS_DICT[slot]][f'{priornum}.{TUG}']) == "0000"


'''Проверка установки качества на источнике внешней синхронизации'''


@pytest.mark.parametrize("priornum, portnum, value",
                         [(priornum, portnum, value)
                          for priornum in [str(x) for x in range(1, 9)]
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
''' ДЛЯ СМД2 нужна другая функция проверки'''


@pytest.mark.skipif(OIDS_SNMP["name"] == "SMD2v2", reason="В данном оборудовании тест провести невозможно")
@pytest.mark.parametrize('slot, portnum, blockport',
                         [(slot, portnum, blockport)
                          for slot, val in SLOTS_DICT.items()
                          if str(slot) in OIDS_SNMP.get("active_slots", {}) and ("STM" in val)
                          for portnum in range(1, 3)
                          for blockport in range(1, OIDS["blockOID"]["quantPort"][SLOTS_DICT[slot]] + 1)])
def test_extSourceID(slot, portnum, blockport):
    block = SLOTS_DICT[slot]
    extSrcID = asyncio.run(extSourceID(str(portnum), slot, str(blockport)))
    assert str(extSrcID) == OIDS["blockOID"]["statusOID"][block] + slot + f'.{blockport}'
    assert bin(int(get_ssh_value(KC_SLOT, '24')))[-int(portnum)] == "1"

    extPort = get_ssh_value(slot, OIDS["extSourceSTM"][block])[-int(portnum)]
    assert OIDS["syncOID"]["prior_dict"][extPort] == str(blockport)


'''Проверка на статус приоритета синхронизации, созданного с участием безаварийного порта'''


@pytest.mark.parametrize("slot, portnum, priornum",
                         [(int(w["dev_slot"]), int(w["dev_port"]), priornum)
                          for w in OIDS_VIAVI["wiring"]
                          if "STM" in w["dev_interface"] and w["dev_slot"] in OIDS_SNMP["active_slots"]
                          for priornum in range(1, 9)
                          if str(asyncio.run(check_alarmPH(int(w["dev_slot"]), int(w["dev_port"])))) not in ["1", "2"]])
def test_prior_statusSTM(slot, portnum, priornum):
    slot = slot
    asyncio.run(clearprior())
    clear_trap_log()
    snmpSTM_set = asyncio.run(set_prior(slot, str(priornum), str(portnum)))
    time.sleep(80)

    prstatustlnt = get_ssh_value(KC_SLOT, '3A')
    assert asyncio.run(prior_status(priornum)) == 1
    assert bin(int(prstatustlnt, 16)).replace('b', '')[-priornum] == '0'

    KCpriorAlarm = get_ssh_value(KC_SLOT, '3A')
    assert bin(int(KCpriorAlarm, 16)).replace('b', '')[-priornum] == "0"
    assert str(asyncio.run(snmp_get(OIDS["syncOID"]["priorACTIVE"]))) == str(int(priornum) - 1)

    trap_log = parse_snmp_log(OIDS["syncOID"]["priorSTATUS"] + f"{priornum}", 2)
    assert trap_log

    tlntSTM_set = get_ssh_value(KC_SLOT,
                                OIDS["priorityREG"][str(priornum)])
    expected_snmp = OIDS["blockOID"]["statusOID"][SLOTS_DICT[slot]] + slot + f'.{portnum}'
    assert str(snmpSTM_set) == expected_snmp and tlntSTM_set != '0000'

    snmpSTM_del = asyncio.run(del_prior(str(priornum)))
    tlntSTM_del = get_ssh_value(KC_SLOT,
                                OIDS["priorityREG"][str(priornum)])
    assert snmpSTM_del == OIDS["equipOID"]["portNull"] and tlntSTM_del == '0000'


'''Проверка уровня качества на входе блоков СТМ'''


@pytest.mark.parametrize("slot, port, ql",
                         [(int(w["dev_slot"]), int(w["dev_port"]), ql)
                          for w in OIDS_VIAVI["wiring"]
                          if "STM" in w["dev_interface"] and str(
                             asyncio.run(check_alarmPH(int(w["dev_slot"]), int(w["dev_port"])))) == "0" and w["dev_slot"] in OIDS_SNMP["active_slots"]
                          for ql in OIDS["qualDICT"]])
def test_QLSTM_get(slot, port, ql):
    slot, port = str(slot), str(port)
    for i in OIDS_VIAVI["wiring"]:
        if i["dev_slot"] == slot and i["dev_port"] == port:
            VIAVI_set_command(SLOTS_DICT[slot], ":SOURCE:SDH:MS:Z1A:BYTE:VIEW", ql, "vc-4", i["viavi_device"],
                              i["viavi_port"])
            reg_value = get_ssh_value(slot, OIDS['syncOID']['stmQLgetREG'][SLOTS_DICT[slot]][port])[-1]
            assert reg_value == OIDS["qualDICT"][ql]
            time.sleep(0.7)
            snmp_ql = asyncio.run(STM1_QL_level(slot, port))
            assert OIDS["qualDICT"][str(snmp_ql)] == OIDS["qualDICT"][ql]


'''Проверка передачи качества ГСЭ по потокам STM'''


@pytest.mark.parametrize("slot, port, ql",
                         [(int(w["dev_slot"]), int(w["dev_port"]), ql)
                          for w in OIDS_VIAVI["wiring"]
                          if "STM" in w["dev_interface"] and str(
                             asyncio.run(check_alarmPH(int(w["dev_slot"]), int(w["dev_port"])))) == "0"
                          for ql in OIDS["qualDICT"]])
def test_QLSTM_set(clear_createSETS, slot, port, ql):
    slot, port = str(slot), str(port)
    for i in OIDS_VIAVI["wiring"]:
        if i["dev_slot"] == slot and i["dev_port"] == port:
            asyncio.run(syncSTMenable(slot, port))
            asyncio.run(setsQL(ql))
            time.sleep(20)
            reg_value = get_ssh_value(slot, OIDS["syncOID"]["stmQLset"][SLOTS_DICT[slot]][port])
            assert OIDS["qualDICT"][str(ql)] in reg_value

            resQLstm = VIAVI_get_command(SLOTS_DICT[slot],
                                         ":SENSE:DATA? INTEGER:SONET:LINE:S1:SYNC:STATUS", "vc-4", i["viavi_device"],
                                         i["viavi_port"])
            expected_ql = OIDS_VIAVI["reqSTMql"][resQLstm[2:-1]]
            assert expected_ql == get_ssh_value(slot, OIDS["syncOID"]["stmQLset"][SLOTS_DICT[slot]][port])


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


@pytest.mark.parametrize('extport, slot, portnum',
                         [pytest.param(extport, slot, portnum, id=f"extport-{extport}, slot-{slot}, portnum-{portnum}")
                          for extport in range(1, 3)
                          for slot in SLOTS_DICT if "STM" in SLOTS_DICT[slot]
                          for portnum in range(1, OIDS["blockOID"]["quantPort"][SLOTS_DICT[slot]] + 1)])
def test_STM_extport(extport, slot, portnum):
    extportvalue = asyncio.run(STM1_ext_port(extport, portnum, slot))
    assert extportvalue == OIDS["blockOID"]["statusOID"][SLOTS_DICT[slot]] + slot + f'.{portnum}'
    assert bin(int(get_ssh_value(find_KS(), '24')))[-int(extport)] == "1"
    STMextport = get_ssh_value(slot, OIDS["syncOID"]["extSourceSTM"][SLOTS_DICT[slot]])

    assert OIDS["syncOID"]["prior_dict"][STMextport[-extport]] == str(portnum)


'''Проверка соответствия текущего уровня качества источника синхронизации на входе блоков СТМ с качеством, записанным в КС'''


@pytest.mark.parametrize('extport, slot, portnum',
                         [pytest.param(extport, slot, portnum, id=f"extport-{extport}, slot-{slot}, portnum-{portnum}")
                          for extport in range(1, 3)
                          for slot in SLOTS_DICT if "STM" in SLOTS_DICT[slot]
                          for portnum in range(1, OIDS["blockOID"]["quantPort"][SLOTS_DICT[slot]] + 1)])
def test_STM_QL_extport(extport, slot, portnum):
    asyncio.run(STM1_ext_port(extport, portnum, slot))
    time.sleep(1)
    extQLKS = get_ssh_value(find_KS(), OIDS["syncOID"]["KCqlGETreg"][str(extport)])
    extQLstm = get_ssh_value(slot, OIDS['syncOID']['stmQLgetREG'][SLOTS_DICT[slot]][str(portnum)])
    assert extQLKS == extQLstm


'''Проверка аварий по порогам статистики для каждого интерфейсного блока и каждого качества на приеме'''

@pytest.mark.skip
@pytest.mark.parametrize('extPort, priornum, slot, portnum, QL ',
                         [(extPort, priornum, int(w["dev_slot"]), int(w["dev_port"]), QL)
                          for w in OIDS_VIAVI["wiring"]
                          if "STM" in w["dev_interface"]
                          for extPort in range(1, 3)
                          for priornum in range(1, 9)
                          if str(asyncio.run(check_alarmPH(int(w["dev_slot"]), int(w["dev_port"])))) in ["0", "64"]
                          for QL in OIDS["qualDICT"]
                          ])
def test_ThresQL_AlarmBlock(extPort, priornum, slot, portnum, QL):
    slot, portnum, priornum = str(slot), str(portnum), str(priornum)
    for i in OIDS_VIAVI["wiring"]:
        if i["dev_slot"] == slot and i["dev_port"] == portnum:
            print(extPort)
            VIAVI_set_command(SLOTS_DICT[slot], ":SOURCE:SDH:MS:Z1A:BYTE:VIEW", QL, "vc-4", i["viavi_device"],
                              i["viavi_port"])
            print(f"QL IS {QL}")
            if QL != "0" and QL != "15":
                for QLblock in [2, 4, 8, 11]:
                    if int(QLblock) >= int(QL) and int(QL) not in [0, 15]:
                        time.sleep(3)
                        print(f"match {QLblock} --- {QL} ")
                        QLalarmdatch = str(asyncio.run(extThreshAlarm(str(extPort))))
                        assert QLalarmdatch == "0"
                        assert bin(int(get_ssh_value(find_KS(), "4e")))[-int(extPort)] in ["0", "b"]
                    else:
                        print(f"BaDmatch {QLblock} --- {QL} ")
                        print(False)
                        time.sleep(10)
                        QLalarmdatch = str(asyncio.run(extThreshAlarm(str(extPort))))
                        assert QLalarmdatch == "2"
                        assert bin(int(get_ssh_value(find_KS(), "4e")))[-int(extPort)] == "1"
            else:
                time.sleep(10)
                assert str(asyncio.run(extThreshAlarm(str(extPort)))) == "2"
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
        assert bd_alarm_get('LOW_QL', OIDS["syncOID"]["extTable"]["extThreshAlarm"] + str(portnum))
        assert bin(int(get_ssh_value(KC_SLOT, "4e")))[-portnum] == "1"
    else:
        assert int(asyncio.run(extThreshAlarm(str(portnum)))) == 2
        assert bd_alarm_get('LOW_QL', OIDS["syncOID"]["extTable"]["extThreshAlarm"] + str(portnum))

        trap_log = parse_snmp_log(OIDS["syncOID"]["extTable"]["extThreshAlarm"] + str(portnum), 2)
        assert OIDS["syncOID"]["extTable"]["extThreshAlarm"] + str(portnum) == trap_log[0]
        assert str(trap_log[1]) in ["1", "2"]

        assert bin(int(get_ssh_value(KC_SLOT, "4e")))[-portnum] == "1"
