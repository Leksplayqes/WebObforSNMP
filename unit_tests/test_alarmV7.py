# -*- coding: utf-8 -*-
import random
import pytest

from unit_tests.SnmpV7alarm import *
from Vivavi.ViaviControl import *
from unit_tests.sshV7 import get_ssh_value, bd_alarm_get
from MainConnectFunc import oids, oidsSNMP, oidsVIAVI, value_parser_OSMK
from TRAP_analyze.ParseTrapLog import parse_snmp_log, clear_trap_log
import asyncio


@pytest.fixture(scope='module')
def E1_VIAVI_test():
    VIAVI_secndStage('E1')
    yield


@pytest.fixture(scope='module')
def E1_loopback():
    set_E1_loopback()


'''Проверка аварий физического порта блоков СТМ. Обязательно подключение VIAVI.
  С помощью VIAVI вводятся аварии, их наличие регестрируется по MIB и регистрам.
  В анализе участвуют только безаварийные порты'''


@pytest.mark.parametrize("slot, portnum, alarmname",
                         [(int(w["dev_slot"]), int(w["dev_port"]), alarmname)
                          for w in OIDS_VIAVI["wiring"]
                          if "STM" in w["dev_interface"] and w["dev_slot"] in OIDS_SNMP["active_slots"]
                          for alarmname in OIDS["main_alarm"]["alarm_viavi"]
                          if str(asyncio.run(check_alarmPH(int(w["dev_slot"]), int(w["dev_port"])))) not in ["1", "2"]])
def test_physical_alarmSTM(slot, portnum, alarmname):
    clear_trap_log()
    non_burst_alarms = {"SD", "EXC", "TIM"}
    for i in OIDS_VIAVI["wiring"]:
        if i["dev_slot"] == slot and i["dev_port"] == portnum:
            VIAVI_secndStage("vc-4", device_name=i["viavi_device"], port_name=i["viavi_port"])
    if alarmname not in non_burst_alarms:
        _handle_standard_alarm(slot, portnum, alarmname)
    elif alarmname == "TIM":
        _handle_tim_alarm(slot, portnum)
    else:
        _handle_burst_alarm(slot, portnum, alarmname)


def _handle_standard_alarm(slot, portnum, alarmname):
    slot, portnum = str(slot), str(portnum)
    time.sleep(0.5)
    is_los = alarmname == "LOS"
    set_val = "OFF" if is_los else "ON"
    reset_val = "ON" if is_los else "OFF"
    block = oidsSNMP()["slots_dict"][slot]
    alarm_oid = OIDS["main_alarm"]["ph_reg_alarmSTM"][block][str(portnum)]
    for i in OIDS_VIAVI["wiring"]:
        if i["dev_slot"] == slot and i["dev_port"] == portnum:
            try:
                VIAVI_set_command(i["viavi_interface"], OIDS["main_alarm"]["alarm_viavi"][alarmname], set_val, "vc-4",
                                  i["viavi_device"],
                                  i["viavi_port"])
                time.sleep(1)
                # Проверка через SSH
                ssh_val = value_parser_OSMK(get_ssh_value(slot, alarm_oid))
                assert ssh_val[OIDS["main_alarm"]["alarm_bit"][alarmname]] == "1"
                # Проверка через SNMP
                assert asyncio.run(check_alarmPH(slot, portnum)) == OIDS["main_alarm"]["alarm_mib_value"][alarmname]
                # Проверка в БД и логах
                alarm_index = f'{OIDS["main_alarm"]["alarm_status"]["physical"][block]}{slot}.{portnum}'
                assert bd_alarm_get(alarmname, alarm_index)
                assert (alarm_index, str(OIDS["main_alarm"]["alarm_mib_value"][alarmname])) == parse_snmp_log(
                    alarm_index, OIDS["main_alarm"]["alarm_mib_value"][alarmname]
                )

                VIAVI_set_command(i["viavi_interface"], OIDS["main_alarm"]["alarm_viavi"][alarmname], reset_val, "vc-4",
                                  i["viavi_device"],
                                  i["viavi_port"])
            except Exception:
                VIAVI_set_command(i["viavi_interface"], OIDS["main_alarm"]["alarm_viavi"][alarmname], reset_val, "vc-4",
                                  i["viavi_device"],
                                  i["viavi_port"])
                raise Exception("Порт проверить невозможно")


def _handle_tim_alarm(slot, portnum):
    slot, portnum = str(slot), str(portnum)
    for i in OIDS_VIAVI["wiring"]:
        if i["dev_slot"] == slot and i["dev_port"] == portnum:
            TD = ''.join(random.choices('123456789qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM', k=15))
            asyncio.run(change_traceTD(slot, portnum, TD[::-1]))
            for f in range(15):
                VIAVI_set_command(i["viavi_interface"], f":SOURCE:SDH:RS:TRACE (@{f})", ord(TD[f]),
                                  "vc-4", i["viavi_device"],
                                  i["viavi_port"])
            time.sleep(2)
            assert asyncio.run(check_alarmPH(slot, portnum)) == OIDS["main_alarm"]["alarm_mib_value"]["TIM"]
            asyncio.run(change_traceExpected(slot, portnum, TD))
            time.sleep(2)
            assert asyncio.run(check_alarmPH(slot, portnum)) == 0


def _handle_burst_alarm(slot, portnum, alarmname):
    slot, portnum = str(slot), str(portnum)
    for i in OIDS_VIAVI["wiring"]:
        if i["dev_slot"] == slot and i["dev_port"] == portnum:
            time.sleep(1)
            rate_val = "1E5" if alarmname == "SD" else "1E4"
            try:
                VIAVI_set_command(i["viavi_interface"], ":SOURCE:SDH:MS:BIP:TYPE", "RATE", "vc-4", i["viavi_device"],
                                  i["viavi_port"])
                VIAVI_set_command(i["viavi_interface"], ":SOURCE:SDH:MS:BIP:RATE", rate_val, "vc-4", i["viavi_device"],
                                  i["viavi_port"])
                VIAVI_set_command(i["viavi_interface"], OIDS["main_alarm"]["alarm_viavi"][alarmname], "ON", "vc-4",
                                  i["viavi_device"],
                                  i["viavi_port"])
                time.sleep(3)
                assert asyncio.run(check_alarmPH(slot, portnum)) == OIDS["main_alarm"]["alarm_mib_value"][alarmname]
                VIAVI_set_command(i["viavi_interface"], OIDS["main_alarm"]["alarm_viavi"][alarmname], "OFF", "vc-4",
                                  i["viavi_device"],
                                  i["viavi_port"])
                time.sleep(2)
            except Exception:
                VIAVI_set_command(i["viavi_interface"], OIDS["main_alarm"]["alarm_viavi"][alarmname], "OFF", "vc-4",
                                  i["viavi_device"],
                                  i["viavi_port"])
                raise


''' Проверка аварий соеденительного порта блоков STM-N.
  Для начала тестирования необходимо указать, где установлен физический шлейф, на этот шлейф будет делаться вся коммутация.
  Перед работой для каждого теста проходит анализ на наличие активных аварий, если такие есть, то тест будет скипнут.
  Далее с Viavi запускается авария, регистрируется по SNMP и **регистрам**.'''


@pytest.mark.parametrize("slot, portnum, alarmname, vc", [
    (int(w["dev_slot"]), int(w["dev_port"]), alarmname, vc)
    for w in OIDS_VIAVI["wiring"]
    if "STM" in w["dev_interface"] and w["dev_slot"] in OIDS_SNMP["active_slots"]
    for alarmname in OIDS["main_alarm"]["alarm_viavi_cnct"]
    for vc in range(1, OIDS["blockOID"]["quantCnctPort"][oidsSNMP()["slots_dict"][str(w["dev_slot"])]] + 1)
])
def test_connective_alarmSTM(slot, portnum, alarmname, vc):
    slot, portnum = str(slot), str(portnum)
    for i in OIDS_VIAVI["wiring"]:
        if i["dev_slot"] == slot and i["dev_port"] == portnum:
            VIAVI_secndStage("vc-4", device_name=i["viavi_device"], port_name=i["viavi_port"])
            asyncio.run(delete_commutation())
            asyncio.run(create_commutationVC4(slot, portnum, vc))

            VIAVI_set_command(i['viavi_interface'], ":SENSE:SDH:CHANNEL:STMN ", str(vc), "vc-4",
                              i["viavi_device"],
                              i["viavi_port"])
            time.sleep(2)

            assert int(asyncio.run(check_alarm_cnct(slot, portnum, vc))) == 0
            if alarmname in ["AU4_AIS", "AU4_LOP", "VC4_UNEQ", "VC4_RDI"]:
                _test_standard_cnct_alarm(slot, portnum, vc, alarmname)
            elif alarmname == "VC4_AIS":
                _test_vcais_alarm(slot, portnum, vc)
            elif alarmname == "AU4_PJE":
                _test_aupje_alarm(slot, portnum, vc)
            elif alarmname == "VC4_PLM":
                _test_vcplm_alarm(slot, portnum, vc)


def _test_standard_cnct_alarm(slot, portnum, vc, alarmname):
    block = oidsSNMP()["slots_dict"][slot]
    clear_trap_log()
    for i in OIDS_VIAVI["wiring"]:
        if i["dev_slot"] == slot and i["dev_port"] == portnum:
            try:
                VIAVI_set_command(i["viavi_interface"], OIDS["main_alarm"]["alarm_viavi_cnct"][alarmname], "", "vc-4",
                                  i["viavi_device"],
                                  i["viavi_port"])
                time.sleep(3)
                assert int(asyncio.run(check_alarm_cnct(slot, portnum, vc))) == \
                       OIDS["main_alarm"]["alarm_mib_valueCnct"][alarmname]

                ssh_value = get_ssh_value(slot,
                                          OIDS["main_alarm"]["cnct_reg_alarm"][block][str(portnum)][
                                              str(vc)])
                bin_value = bin(int(ssh_value, 16))[2:].zfill(8)
                assert bin_value[OIDS["main_alarm"]["alarm_bit_cnct"][alarmname]] == "1"

                alarm_index = f'{OIDS["main_alarm"]["alarm_status"]["connective"][block]}{slot}.{portnum}.{vc}'
                assert bd_alarm_get(alarmname, alarm_index)
                assert (alarm_index, str(OIDS["main_alarm"]["alarm_mib_valueCnct"][alarmname])) == parse_snmp_log(
                    alarm_index, OIDS["main_alarm"]["alarm_mib_valueCnct"][alarmname])
            except Exception:
                raise AssertionError(f"Тест аварии {alarmname} не прошел")
            finally:
                VIAVI_set_command(i["viavi_interface"], OIDS["main_alarm"]["alarm_viavi_cnct"][alarmname], "", "vc-4",
                                  i["viavi_device"],
                                  i["viavi_port"])


def _test_vcais_alarm(slot, portnum, vc):
    alarmname = "VC4_AIS"
    clear_trap_log()
    block = oidsSNMP()["slots_dict"][slot]
    for i in OIDS_VIAVI["wiring"]:
        if i["dev_slot"] == slot and i["dev_port"] == portnum:
            try:
                VIAVI_set_command(i["viavi_interface"], OIDS["main_alarm"]["alarm_viavi_cnct"][alarmname], "255",
                                  "vc-4",
                                  i["viavi_device"],
                                  i["viavi_port"])
                time.sleep(3)
                assert asyncio.run(check_alarm_cnct(slot, portnum, vc)) == OIDS["main_alarm"]["alarm_mib_valueCnct"][
                    alarmname]
                alarm_oid = f'{OIDS["main_alarm"]["alarm_status"]["connective"][block]}{slot}.{portnum}.{vc}'
                assert bd_alarm_get(alarmname, alarm_oid)
                assert (alarm_oid, str(OIDS["main_alarm"]["alarm_mib_valueCnct"][alarmname])) == parse_snmp_log(
                    alarm_oid, OIDS["main_alarm"]["alarm_mib_valueCnct"][alarmname])
            except Exception:
                raise AssertionError("Тест аварии VCAIS не прошел")
            finally:
                VIAVI_set_command(i["viavi_interface"], OIDS["main_alarm"]["alarm_viavi_cnct"][alarmname], "254",
                                  "vc-4",
                                  i["viavi_device"],
                                  i["viavi_port"])


def _test_aupje_alarm(slot, portnum, vc):
    clear_trap_log()
    alarmname = "AU4_PJE"
    block = oidsSNMP()["slots_dict"][slot]
    for i in OIDS_VIAVI["wiring"]:
        if i["dev_slot"] == slot and i["dev_port"] == portnum:
            try:
                VIAVI_set_command(i["viavi_interface"], OIDS["main_alarm"]["alarm_viavi_cnct"][alarmname], "INTERNAL",
                                  "vc-4",
                                  i["viavi_device"],
                                  i["viavi_port"])
                VIAVI_set_command(i["viavi_interface"], ":OUTPUT:CLOCK:OFFSET ", "50",
                                  "vc-4",
                                  i["viavi_device"],
                                  i["viavi_port"])
                time.sleep(3)

                assert asyncio.run(check_alarm_cnct(slot, portnum, vc)) == \
                       OIDS["main_alarm"]["alarm_mib_valueCnct"][alarmname]
                alarm_oid = f'{OIDS["main_alarm"]["alarm_status"]["connective"][block]}{slot}.{portnum}.{vc}'
                assert bd_alarm_get(alarmname, alarm_oid)
                assert (alarm_oid, str(OIDS["main_alarm"]["alarm_mib_valueCnct"][alarmname])) == parse_snmp_log(
                    alarm_oid, OIDS["main_alarm"]["alarm_mib_valueCnct"][alarmname])
            except Exception:
                raise AssertionError("Тест аварии AUPJE не прошел")
            finally:
                VIAVI_set_command(i["viavi_interface"], OIDS["main_alarm"]["alarm_viavi_cnct"][alarmname], "RECOVERED",
                                  "vc-4",
                                  i["viavi_device"],
                                  i["viavi_port"])


def _test_vcplm_alarm(slot, portnum, vc):
    clear_trap_log()
    alarmname = "VC4_PLM"
    alarm_index = OIDS["main_alarm"]["alarm_mib_valueCnct"][alarmname]
    block = oidsSNMP()["slots_dict"][slot]
    for i in OIDS_VIAVI["wiring"]:
        if i["dev_slot"] == slot and i["dev_port"] == portnum:
            try:
                VIAVI_set_command(i["viavi_interface"], OIDS["main_alarm"]["alarm_viavi_cnct"][alarmname], "012",
                                  "vc-4",
                                  i["viavi_device"],
                                  i["viavi_port"])
                time.sleep(4)

                assert asyncio.run(check_alarm_cnct(slot, portnum, vc)) == \
                       OIDS["main_alarm"]["alarm_mib_valueCnct"][alarmname]
                alarm_oid = f'{OIDS["main_alarm"]["alarm_status"]["connective"][block]}{slot}.{portnum}.{vc}'
                assert bd_alarm_get(alarmname, alarm_oid)
                assert (alarm_oid, str(OIDS["main_alarm"]["alarm_mib_valueCnct"][alarmname])) == parse_snmp_log(
                    alarm_oid, OIDS["main_alarm"]["alarm_mib_valueCnct"][alarmname])
            except Exception:
                raise AssertionError("Тест аварии VCPLM не прошел")
            finally:
                VIAVI_set_command(i["viavi_interface"], OIDS["main_alarm"]["alarm_viavi_cnct"][alarmname], "254",
                                  "vc-4",
                                  i["viavi_device"],
                                  i["viavi_port"])


''' Нужен VIAVI, блок СТМ любой и естественно Е1.
Иcследуемые порты обязательно должны быть физически зашлейфены сами на себя. МОЖНО РЕАЛИЗОВАТЬ ПО ПРОГРАММНОМУ ШЛЕЙФУ!!!!
Тестируются блоки 21Е1 и 63Е1, если на момент начала теста по физическому порту была авария E1-AIS (используется как идентификатор наличия шлейфа)
Далее по очереди для каждого порта сеттятся аварии и проверяется их наличие как в регистрах блока так и по SNMP.
Тест долгий, каждая авария анализруется около 7-8 секунд, т.е примерно 45 секунд на порт.
ВНИМАНИЕ!!!
В тесте используется только ПЕРВЫЙ ПОРТ VIAVI!!!!
'''

''' Необходимо сделать создание теста на VIAVI при запуске группы Е1 тестов.'''


@pytest.mark.parametrize('slot, alarmname, vc', [
    (slot, alarmname, vc)
    for slot, module in oidsSNMP()["slots_dict"].items()
    if "E1" in module and slot in OIDS_SNMP["active_slots"]
    for alarmname in OIDS["main_alarm"]["alarm_viavi_cnctE1"]
    for vc in range(1, OIDS["blockOID"]["quantPort"][module] + 1)
])
def test_connective_alarmE1(E1_VIAVI_test, slot, alarmname, vc):
    wiring_block = OIDS_VIAVI["wiring"][0]
    STMslot, STMport = wiring_block["dev_slot"], wiring_block["dev_port"]
    VIAVI_secndStage("vc-12", device_name=wiring_block["viavi_device"], port_name=wiring_block["viavi_port"])
    asyncio.run(delete_commutation())
    asyncio.run(create_commutationE1(slot, vc, STMslot, STMport))
    time.sleep(10)

    if alarmname in ["TUAIS", "VCUNEQ", "VCRDI"]:
        _test_standard_e1_alarm(slot, vc, alarmname, wiring_block)
    elif alarmname in ["VCAIS", "VCPLM"]:
        _test_vcaplm_e1_alarm(slot, vc, alarmname, wiring_block)
    elif alarmname == "TUPJE":
        _test_tupje_e1_alarm(slot, vc, wiring_block)
    elif alarmname == "VCTIM":
        _test_vctim_e1_alarm(slot, vc, wiring_block)


def _test_standard_e1_alarm(slot, vc, alarmname, wiring_block):
    try:
        VIAVI_set_command(wiring_block["viavi_interface"], OIDS["main_alarm"]["alarm_viavi_cnctE1"][alarmname], "ON")
        time.sleep(2)

        ssh_value = get_ssh_value(slot, OIDS["main_alarm"]["cnct_reg_alarmE1"][oidsSNMP()["slots_dict"][slot]][str(vc)])
        parsed_value = value_parser_OSMK(ssh_value)
        assert parsed_value[OIDS["main_alarm"]["alarm_bit_cnctE1"][alarmname]] == "1"

        assert asyncio.run(check_alarm_cnctE1(slot, vc)) == OIDS["main_alarm"]["alarm_mib_valueE1"][alarmname]

        time.sleep(2)
    except Exception:
        raise AssertionError(f"Тест аварии {alarmname} не прошел")
    finally:
        VIAVI_set_command(wiring_block["viavi_interface"], OIDS["main_alarm"]["alarm_viavi_cnctE1"][alarmname], "OFF")


def _test_vcaplm_e1_alarm(slot, vc, alarmname, wiring_block):
    set_value = "14" if alarmname == "VCAIS" else "10"

    try:
        VIAVI_set_command(wiring_block["viavi_interface"], OIDS["main_alarm"]["alarm_viavi_cnctE1"][alarmname], set_value)
        time.sleep(2)

        ssh_value = get_ssh_value(slot, OIDS["main_alarm"]["cnct_reg_alarmE1"][oidsSNMP()["slots_dict"][slot]][str(vc)])
        parsed_value = value_parser_OSMK(ssh_value)
        assert parsed_value[OIDS["main_alarm"]["alarm_bit_cnctE1"][alarmname]] == "1"

        assert asyncio.run(check_alarm_cnctE1(slot, vc)) == OIDS["main_alarm"]["alarm_mib_valueE1"][alarmname]

    except Exception:
        raise AssertionError(f"Тест аварии {alarmname} не прошел")
    finally:
        VIAVI_set_command(wiring_block["viavi_interface"], OIDS["main_alarm"]["alarm_viavi_cnctE1"][alarmname], "4")


def _test_tupje_e1_alarm(slot, vc, wiring_block):
    try:
        VIAVI_set_command(wiring_block["viavi_interface"], OIDS["main_alarm"]["alarm_viavi_cnctE1"]["TUPJE"], "INTERNAL")
        time.sleep(2)

        ssh_value = get_ssh_value(slot, OIDS["main_alarm"]["cnct_reg_alarmE1"][oidsSNMP()["slots_dict"][slot]][str(vc)])
        parsed_value = value_parser_OSMK(ssh_value)
        assert parsed_value[OIDS["main_alarm"]["alarm_bit_cnctE1"]["TUPJE"]] == "1"

        assert asyncio.run(check_alarm_cnctE1(slot, vc)) == OIDS["main_alarm"]["alarm_mib_valueE1"]["TUPJE"]

    except Exception:
        raise AssertionError("Тест аварии TUPJE не прошел")
    finally:
        VIAVI_set_command(wiring_block["viavi_interface"], OIDS["main_alarm"]["alarm_viavi_cnctE1"]["TUPJE"], "RECOVERED")


def _test_vctim_e1_alarm(slot, vc, wiring_block):
    block = oidsSNMP()["slots_dict"][slot]
    try:
        TD = ''.join(random.choices('123456789qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM', k=15))
        asyncio.run(change_traceTDE1(block, vc, "J2       "))
        for i in range(15):
            VIAVI_set_command(wiring_block["viavi_interface"],
                              f":SOURCE:SDH:LP:OVERHEAD:TRACE (@{i})", value=ord(TD[i]))
        time.sleep(1)
        assert asyncio.run(check_alarm_cnctE1(block, vc)) == OIDS["main_alarm"]["alarm_mib_valueE1"]["VCTIM"]
        asyncio.run(change_traceTDE1(block, vc, TD))
        time.sleep(1)
        assert asyncio.run(check_alarmPH(block, vc)) == 0
    except Exception:
        raise AssertionError("Тест аварии VCTIM не прошел")
    finally:
        TD = "J2       "
        asyncio.run(change_traceTDE1(block, vc, "J2       "))
        for i in range(15):
            VIAVI_set_command(wiring_block["viavi_interface"], f":SOURCE:SDH:LP:OVERHEAD:TRACE (@{i})", value=ord(TD[i]))


''' Тесть исключительно только для первого VC-4 в блоке Eth1000
VIAVI подключается к блоку СТМ(любом) на Eth1000 ставим физ шлейф.
коммутация создается автоматически, далее сеттятся по очереди аварии.
TRAP не прикручены, как и проверка устранения аварий!'''


@pytest.mark.parametrize('block, portnum, alarmname, vc', [(block, portnum, alarmname, vc)
                                                           for block in [block for block in oidsSNMP()["slots_dict"] if
                                                                         "Eth1000" in block]
                                                           for portnum in range(1, 2)
                                                           for alarmname in OIDS["main_alarm"]["alarm_viavi_cnctGE"]
                                                           for vc in range(1, 2)])
def test_connective_alarmGE(block, portnum, alarmname, vc):
    asyncio.run(delete_commutation())
    asyncio.run(create_commutationGE(block, vc))
    VIAVI_set_command(oidsVIAVI()["settings"]["NumOne"]["typeofport"]["Port1"], ":SOURCE:SDH:HP:C2:BYTE", 27)
    VIAVI_set_command(oidsVIAVI()["settings"]["NumOne"]["typeofport"]["Port1"], ":SOURCE:SDH:STMN:CHANNEL ", vc)
    VIAVI_set_command(oidsVIAVI()["settings"]["NumOne"]["typeofport"]["Port1"], ":OUTPUT:CLOCK:SOURCE", "RECOVERED")
    time.sleep(3)
    assert asyncio.run(check_alarm_cnct(block, portnum, vc)) == 0 or 256
    if alarmname in ["AUAIS", "VCUNEQ", "VCRDI"]:
        VIAVI_set_command(oidsVIAVI()["settings"]["NumOne"]["typeofport"]["Port1"],
                          OIDS["main_alarm"]["alarm_viavi_cnctGE"][alarmname], "ON")
        time.sleep(1)
    elif alarmname in ["VCAIS", "VCPLM"]:
        VIAVI_set_command(oidsVIAVI()["settings"]["NumOne"]["typeofport"]["Port1"],
                          OIDS["main_alarm"]["alarm_viavi_cnctGE"][alarmname], "255" if alarmname == "VCAIS" else "207")
        time.sleep(1)
        '''Надо доделать, ВИАВИ должен быть подключен к порту и тогда можно менять только и, этого хватит для аварии'''
    elif alarmname == "VCTIM":
        pass
    elif alarmname in ["AUPJE"]:
        asyncio.run(
            snmp_set("1.3.6.1.4.1.5756.3.3.2.12.5.5.2.1.6." + str(oidsSNMP()["slots_dict"][block] + f'.1.{portnum}'),
                     Integer(746)))
        VIAVI_set_command(oidsVIAVI()["settings"]["NumOne"]["typeofport"]["Port1"],
                          OIDS["main_alarm"]["alarm_viavi_cnctGE"][alarmname], "INTERNAL")
        time.sleep(2)
    try:
        assert asyncio.run(check_alarm_cnct(block, portnum, vc)) == OIDS["main_alarm"]["alarm_mib_valueCnctGE"][
            alarmname]
        assert \
            value_parser_OSMK(get_ssh_value(block, OIDS["main_alarm"]["cnct_reg_alarm"][block][str(portnum)][str(vc)]))[
                OIDS["main_alarm"]["alarm_bit_cnctGE"][alarmname]] == "1"
        if alarmname in ["AUAIS", "VCUNEQ", "VCRDI"]:
            VIAVI_set_command(oidsVIAVI()["settings"]["NumOne"]["typeofport"]["Port1"],
                              OIDS["main_alarm"]["alarm_viavi_cnctGE"][alarmname], "OFF")
            time.sleep(1)
    except:
        VIAVI_set_command(oidsVIAVI()["settings"]["NumOne"]["typeofport"]["Port1"],
                          OIDS["main_alarm"]["alarm_viavi_cnctGE"][alarmname], "OFF")
        assert False
