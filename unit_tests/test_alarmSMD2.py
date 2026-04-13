# -*- coding: utf-8 -*-
import random
import pytest

from SnmpV7alarm import *
from Vivavi.ViaviControl import *
from sshV7 import get_ssh_value, bd_alarm_get
from MainConnectFunc import oids, oidsSNMP, oidsVIAVI
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


@pytest.mark.parametrize('slot, portnum, alarmname', [(slot, portnum, alarmname)
                                                      for slot in [slot for slot in oidsSNMP["slots_dict"] if
                                                                   "STM" in oidsSNMP["slots_dict"][slot] and any(
                                                                       slot in w["dev_slot"] for w in
                                                                       oidsVIAVI()["wiring"])]
                                                      for portnum in
                                                      [portnum for portnum in
                                                       range(1, OIDS["blockOID"]["quantPort"][
                                                           oidsSNMP["slots_dict"][slot]] + 1)
                                                       if [slot, str(portnum)] != oidsSNMP["loopback"] and asyncio.run(
                                                          check_alarmPH(slot, portnum)) in (0, 64) and any(
                                                          portnum in w["dev_port"] for w in oidsVIAVI()["wiring"])]
                                                      for alarmname in oids["main_alarm"]["alarm_viavi"]])
def test_physical_alarmSTM(slot, portnum, alarmname):
    clear_trap_log()
    non_burst_alarms = {"SD", "EXC", "TIM"}

    if alarmname not in non_burst_alarms:
        _handle_standard_alarm(slot, portnum, alarmname)
    elif alarmname == "TIM":
        _handle_tim_alarm(slot, portnum)
    else:
        _handle_burst_alarm(slot, portnum, alarmname)


def _handle_standard_alarm(slot, portnum, alarmname):
    time.sleep(0.5)
    is_los = alarmname == "LOS"
    set_val = "OFF" if is_los else "ON"
    reset_val = "ON" if is_los else "OFF"
    block = oidsSNMP["slots_dict"][slot]
    alarm_oid = oids["main_alarm"]["ph_reg_alarmSTM"][block][str(portnum)]

    try:
        VIAVI_set_command(block, oids["main_alarm"]["alarm_viavi"][alarmname], set_val, )
        time.sleep(1)
        # Проверка через SSH
        ssh_val = value_parcer_OSMK(get_ssh_value(slot, alarm_oid))
        assert ssh_val[oids["main_alarm"]["alarm_bit"][alarmname]] == "1"
        # Проверка через SNMP
        assert asyncio.run(check_alarmPH(slot, portnum)) == oids["main_alarm"]["alarm_mib_value"][alarmname]
        # Проверка в БД и логах
        alarm_index = f'{oids["main_alarm"]["alarm_status"]["physical"][block]}{slot}.{portnum}'
        assert bd_alarm_get(alarmname, alarm_index)
        assert (alarm_index, str(oids["main_alarm"]["alarm_mib_value"][alarmname])) == parse_snmp_log(
            alarm_index, oids["main_alarm"]["alarm_mib_value"][alarmname]
        )
        # Сброс аварии
        VIAVI_set_command(block, oids["main_alarm"]["alarm_viavi"][alarmname], reset_val)
    except Exception:
        VIAVI_set_command(block, oids["main_alarm"]["alarm_viavi"][alarmname], reset_val)
        raise Exception("Порт проверить невозможно")


def _handle_tim_alarm(slot, portnum):
    try:
        # Генерация случайной строки
        TD = ''.join(random.choices('123456789qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM', k=15))
        asyncio.run(change_traceTD(slot, portnum, TD[::-1]))
        # Установка трасса VIAVI
        for i in range(15):
            VIAVI_set_command(oidsSNMP["slots_dict"][slot], f":SOURCE:SDH:RS:TRACE (@{i})", value=ord(TD[i]))
        time.sleep(1)
        assert asyncio.run(check_alarmPH(slot, portnum)) == oids["main_alarm"]["alarm_mib_value"]["TIM"]
        # Восстановление ожидаемого трасса
        asyncio.run(change_traceExpected(slot, portnum, TD))
        time.sleep(1)
        assert asyncio.run(check_alarmPH(slot, portnum)) == 0
    except Exception:
        TD = "J0       "
        asyncio.run(change_traceExpected(slot, portnum, TD))
        for i in range(9):  # Длина "J0       " - 9 символов
            VIAVI_set_command(oidsSNMP["slots_dict"][slot], f":SOURCE:SDH:RS:TRACE (@{i})", value=ord(TD[i]))
        raise  # Перевызов исключения


def _handle_burst_alarm(slot, portnum, alarmname):
    time.sleep(1)
    block = oidsSNMP["slots_dict"][slot]
    rate_val = "1E5" if alarmname == "SD" else "1E3"
    try:
        VIAVI_set_command(block, ":SOURCE:SDH:MS:BIP:TYPE", "RATE")
        VIAVI_set_command(block, ":SOURCE:SDH:MS:BIP:RATE", rate_val)
        VIAVI_set_command(block, oids["main_alarm"]["alarm_viavi"][alarmname], "ON")
        time.sleep(3)
        assert asyncio.run(check_alarmPH(slot, portnum)) == oids["main_alarm"]["alarm_mib_value"][alarmname]
        VIAVI_set_command(block, oids["main_alarm"]["alarm_viavi"][alarmname], "OFF")
        time.sleep(2)
    except Exception:
        VIAVI_set_command(block, oids["main_alarm"]["alarm_viavi"][alarmname], "OFF")
        raise


''' Проверка аварий соеденительного порта блоков STM-N.
  Для начала тестирования необходимо указать, где установлен физический шлейф, на этот шлейф будет делаться вся коммутация.
  Перед работой для каждого теста проходит анализ на наличие активных аварий, если такие есть, то тест будет скипнут.
  Далее с Viavi запускается авария, регистрируется по SNMP и **регистрам**.'''


@pytest.mark.parametrize('slot, portnum, alarmname, vc', [(slot, portnum, alarmname, vc)
                                                          for slot in
                                                          [slot for slot in oidsSNMP["slots_dict"] if
                                                           "STM" in oidsSNMP["slots_dict"][slot]]
                                                          for portnum in [portnum for portnum in
                                                                          range(1, OIDS["blockOID"]["quantPort"][
                                                                              oidsSNMP["slots_dict"][slot]] + 1) if
                                                                          [slot, str(portnum)] != oidsSNMP[
                                                                              "loopback"] and asyncio.run(
                                                                              check_alarmPH(slot, portnum)) in (0, 64)]
                                                          for alarmname in oids["main_alarm"]["alarm_viavi_cnct"]
                                                          for vc in range(1, oids["quantCnctPort"][
        oidsSNMP["slots_dict"][slot]] + 1)])
def test_connective_alarmSTM(slot, portnum, alarmname, vc):
    """Тест для проверки аварий связности STM"""
    asyncio.run(delete_commutation())
    asyncio.run(create_commutationVC4(slot, portnum, vc))

    block = oidsSNMP["slots_dict"][slot]
    VIAVI_set_command(block, ":SENSE:SDH:CHANNEL:STMN", vc)
    time.sleep(2)

    assert int(asyncio.run(check_alarm_cnct(slot, portnum, vc))) == 0

    if alarmname in ["AUAIS", "AULOP", "VCUNEQ", "VCRDI"]:
        _test_standard_cnct_alarm(slot, portnum, vc, alarmname, block)
    elif alarmname == "VCAIS":
        _test_vcais_alarm(slot, portnum, vc, block)
    elif alarmname == "AUPJE":
        _test_aupje_alarm(slot, portnum, vc, block)
    elif alarmname == "VCPLM":
        _test_vcplm_alarm(slot, portnum, vc, block)


def _test_standard_cnct_alarm(slot, portnum, vc, alarmname, viavi_slot):
    """Тест стандартных аварий связности"""
    block = oidsSNMP["slots_dict"][slot]
    try:
        VIAVI_set_command(viavi_slot, oids["main_alarm"]["alarm_viavi_cnct"][alarmname], "")
        time.sleep(3)

        # Проверка через SNMP
        assert int(asyncio.run(check_alarm_cnct(slot, portnum, vc))) == \
               oids["main_alarm"]["alarm_mib_valueCnct"][alarmname]

        # Проверка через SSH
        ssh_value = get_ssh_value(slot, oids["main_alarm"]["cnct_reg_alarm"][viavi_slot][str(portnum)][str(vc)])
        bin_value = bin(int(ssh_value, 16))[2:].zfill(8)
        assert bin_value[oids["main_alarm"]["alarm_bit_cnct"][alarmname]] == "1"

        # Проверка TRAP сообщений и аварий в БД (hw_alarm)
        alarm_index = f'{oids["main_alarm"]["alarm_status"]["connective"][block]}{slot}.{portnum}'
        assert bd_alarm_get(alarmname, alarm_index)
        assert (alarm_index, str(oids["main_alarm"]["alarm_mib_valueCnct"][alarmname])) == parse_snmp_log(
            alarm_index, oids["main_alarm"]["alarm_mib_valueCnct"][alarmname])

    except Exception:
        raise AssertionError(f"Тест аварии {alarmname} не прошел")
    finally:
        VIAVI_set_command(viavi_slot, oids["main_alarm"]["alarm_viavi_cnct"][alarmname], "")


def _test_vcais_alarm(slot, portnum, vc, viavi_slot):
    """Тест аварии VCAIS"""
    alarmname = "VC4_AIS"
    alarm_index = oids["main_alarm"]["alarm_mib_valueCnct"][alarmname]
    try:
        VIAVI_set_command(viavi_slot, oids["main_alarm"]["alarm_viavi_cnct"][alarmname], "255")
        time.sleep(3)
        assert asyncio.run(check_alarm_cnct(slot, portnum, vc)) == alarm_index
        assert bd_alarm_get(alarmname, alarm_index)
        assert (alarm_index, str(oids["main_alarm"]["alarm_mib_valueCnct"][alarmname])) == parse_snmp_log(
            alarm_index, oids["main_alarm"]["alarm_mib_valueCnct"][alarmname])
    except Exception:
        raise AssertionError("Тест аварии VCAIS не прошел")
    finally:
        VIAVI_set_command(viavi_slot, oids["main_alarm"]["alarm_viavi_cnct"][alarmname], "254")


def _test_aupje_alarm(slot, portnum, vc, viavi_slot):
    """Тест аварии AUPJE"""
    alarmname = "AU4_PJE"
    alarm_index = oids["main_alarm"]["alarm_mib_valueCnct"][alarmname]
    try:
        VIAVI_set_command(viavi_slot, oids["main_alarm"]["alarm_viavi_cnct"][alarmname], "INTERNAL")
        time.sleep(3)

        assert asyncio.run(check_alarm_cnct(slot, portnum, vc)) == \
               oids["main_alarm"]["alarm_mib_valueCnct"][alarmname]
        assert bd_alarm_get(alarmname, alarm_index)
        assert (alarm_index, str(oids["main_alarm"]["alarm_mib_valueCnct"][alarmname])) == parse_snmp_log(
            alarm_index, oids["main_alarm"]["alarm_mib_valueCnct"][alarmname])
    except Exception:
        raise AssertionError("Тест аварии AUPJE не прошел")
    finally:
        VIAVI_set_command(viavi_slot, oids["main_alarm"]["alarm_viavi_cnct"][alarmname], "RECOVERED")


def _test_vcplm_alarm(slot, portnum, vc, viavi_slot):
    """Тест аварии VCPLM"""
    alarmname = "VC4_PLM"
    alarm_index = oids["main_alarm"]["alarm_mib_valueCnct"][alarmname]
    try:
        VIAVI_set_command(viavi_slot, oids["main_alarm"]["alarm_viavi_cnct"][alarmname], "012")
        time.sleep(3)

        assert asyncio.run(check_alarm_cnct(slot, portnum, vc)) == \
               oids["main_alarm"]["alarm_mib_valueCnct"][alarmname]
        assert bd_alarm_get(alarmname, alarm_index)
        assert (alarm_index, str(oids["main_alarm"]["alarm_mib_valueCnct"][alarmname])) == parse_snmp_log(
            alarm_index, oids["main_alarm"]["alarm_mib_valueCnct"][alarmname])
    except Exception:
        raise AssertionError("Тест аварии VCPLM не прошел")
    finally:
        VIAVI_set_command(viavi_slot, oids["main_alarm"]["alarm_viavi_cnct"][alarmname], "254")


'''Как всегда работает как говно.
Нужен VIAVI, блок СТМ любой и естественно Е1.
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
    for slot in [slot for slot in oidsSNMP["slots_dict"] if "E1" in oidsSNMP["slots_dict"][slot]]
    for alarmname in oids["main_alarm"]["alarm_viavi_cnctE1"]
    for vc in range(1, OIDS["blockOID"]["quantPort"][oidsSNMP["slots_dict"][slot]] + 1)
])
def test_connective_alarmE1(E1_VIAVI_test, slot, alarmname, vc):
    """Тест для проверки аварий VC12"""
    asyncio.run(delete_commutation())
    asyncio.run(create_commutationE1(slot, vc))
    time.sleep(1)

    if alarmname in ["TUAIS", "VCUNEQ", "VCRDI"]:
        _test_standard_e1_alarm(slot, vc, alarmname)
    elif alarmname in ["VCAIS", "VCPLM"]:
        _test_vcaplm_e1_alarm(slot, vc, alarmname)
    elif alarmname == "TUPJE":
        _test_tupje_e1_alarm(slot, vc)
    elif alarmname == "VCTIM":
        _test_vctim_e1_alarm(slot, vc)


def _test_standard_e1_alarm(slot, vc, alarmname):
    """Тест стандартных аварий E1 (TUAIS, VCUNEQ, VCRDI)"""
    viavi_port = oidsVIAVI["settings"]["NumOne"]["typeofport"]["Port1"]
    try:
        VIAVI_set_command(viavi_port, oids["main_alarm"]["alarm_viavi_cnctE1"][alarmname], "ON")
        time.sleep(2)

        # Проверка через SSH
        ssh_value = get_ssh_value(slot, oids["main_alarm"]["cnct_reg_alarmE1"][oidsSNMP["slots_dict"][slot]][str(vc)])
        parsed_value = value_parcer_OSMK(ssh_value)
        assert parsed_value[oids["main_alarm"]["alarm_bit_cnctE1"][alarmname]] == "1"

        # Проверка через SNMP
        assert asyncio.run(check_alarm_cnctE1(slot, vc)) == oids["main_alarm"]["alarm_mib_valueE1"][alarmname]

        time.sleep(2)
    except Exception:
        raise AssertionError(f"Тест аварии {alarmname} не прошел")
    finally:
        VIAVI_set_command(viavi_port, oids["main_alarm"]["alarm_viavi_cnctE1"][alarmname], "OFF")


def _test_vcaplm_e1_alarm(slot, vc, alarmname):
    """Тест аварий VCAIS и VCPLM для E1"""
    viavi_port = oidsVIAVI["settings"]["NumOne"]["typeofport"]["Port1"]
    set_value = "14" if alarmname == "VCAIS" else "10"

    try:
        VIAVI_set_command(viavi_port, oids["main_alarm"]["alarm_viavi_cnctE1"][alarmname], set_value)
        time.sleep(2)

        # Проверка через SSH
        ssh_value = get_ssh_value(slot, oids["main_alarm"]["cnct_reg_alarmE1"][oidsSNMP["slots_dict"][slot]][str(vc)])
        parsed_value = value_parcer_OSMK(ssh_value)
        assert parsed_value[oids["main_alarm"]["alarm_bit_cnctE1"][alarmname]] == "1"

        # Проверка через SNMP
        assert asyncio.run(check_alarm_cnctE1(slot, vc)) == oids["main_alarm"]["alarm_mib_valueE1"][alarmname]

    except Exception:
        raise AssertionError(f"Тест аварии {alarmname} не прошел")
    finally:
        VIAVI_set_command(viavi_port, oids["main_alarm"]["alarm_viavi_cnctE1"][alarmname], "4")


def _test_tupje_e1_alarm(slot, vc):
    """Тест аварии TUPJE для E1"""
    viavi_port = oidsVIAVI["settings"]["NumOne"]["typeofport"]["Port1"]

    try:
        VIAVI_set_command(viavi_port, oids["main_alarm"]["alarm_viavi_cnctE1"]["TUPJE"], "INTERNAL")
        time.sleep(2)

        # Проверка через SSH
        ssh_value = get_ssh_value(slot, oids["main_alarm"]["cnct_reg_alarmE1"][oidsSNMP["slots_dict"][slot]][str(vc)])
        parsed_value = value_parcer_OSMK(ssh_value)
        assert parsed_value[oids["main_alarm"]["alarm_bit_cnctE1"]["TUPJE"]] == "1"

        # Проверка через SNMP
        assert asyncio.run(check_alarm_cnctE1(slot, vc)) == oids["main_alarm"]["alarm_mib_valueE1"]["TUPJE"]

    except Exception:
        raise AssertionError("Тест аварии TUPJE не прошел")
    finally:
        VIAVI_set_command(viavi_port, oids["main_alarm"]["alarm_viavi_cnctE1"]["TUPJE"], "RECOVERED")


def _test_vctim_e1_alarm(slot, vc):
    """Тест аварии VCTIM для E1"""
    block = oidsSNMP["slots_dict"][slot]
    try:
        TD = ''.join(random.choices('123456789qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM', k=15))
        asyncio.run(change_traceTDE1(block, vc, "J2       "))
        for i in range(15):
            VIAVI_set_command(oidsVIAVI["settings"]["NumOne"]["typeofport"]["Port1"],
                              f":SOURCE:SDH:LP:OVERHEAD:TRACE (@{i})", value=ord(TD[i]))
        time.sleep(1)
        assert asyncio.run(check_alarm_cnctE1(block, vc)) == oids["main_alarm"]["alarm_mib_valueE1"]["VCTIM"]
        asyncio.run(change_traceTDE1(block, vc, TD))
        time.sleep(1)
        assert asyncio.run(check_alarmPH(block, vc)) == 0
    except Exception:
        raise AssertionError("Тест аварии VCTIM не прошел")
    finally:
        TD = "J2       "
        asyncio.run(change_traceTDE1(block, vc, "J2       "))
        for i in range(15):
            VIAVI_set_command(block, f":SOURCE:SDH:LP:OVERHEAD:TRACE (@{i})", value=ord(TD[i]))


''' Тесть исключительно только для первого VC-4 в блоке Eth1000
VIAVI подключается к блоку СТМ(любом) на Eth1000 ставим физ шлейф.
коммутация создается автоматически, далее сеттятся по очереди аварии.
TRAP не прикручены, как и проверка устранения аварий!'''


@pytest.mark.parametrize('block, portnum, alarmname, vc', [(block, portnum, alarmname, vc)
                                                           for block in [block for block in oidsSNMP["slots_dict"] if
                                                                         "Eth1000" in block]
                                                           for portnum in range(1, 2)
                                                           for alarmname in oids["main_alarm"]["alarm_viavi_cnctGE"]
                                                           for vc in range(1, 2)])
def test_connective_alarmGE(block, portnum, alarmname, vc):
    asyncio.run(delete_commutation())
    asyncio.run(create_commutationGE(block, vc))
    VIAVI_set_command(oidsVIAVI["settings"]["NumOne"]["typeofport"]["Port1"], ":SOURCE:SDH:HP:C2:BYTE", 27)
    VIAVI_set_command(oidsVIAVI["settings"]["NumOne"]["typeofport"]["Port1"], ":SOURCE:SDH:STMN:CHANNEL ", vc)
    VIAVI_set_command(oidsVIAVI["settings"]["NumOne"]["typeofport"]["Port1"], ":OUTPUT:CLOCK:SOURCE", "RECOVERED")
    time.sleep(3)
    assert asyncio.run(check_alarm_cnct(block, portnum, vc)) == 0 or 256
    if alarmname in ["AUAIS", "VCUNEQ", "VCRDI"]:
        VIAVI_set_command(oidsVIAVI["settings"]["NumOne"]["typeofport"]["Port1"],
                          oids["main_alarm"]["alarm_viavi_cnctGE"][alarmname], "ON")
        time.sleep(1)
    elif alarmname in ["VCAIS", "VCPLM"]:
        VIAVI_set_command(oidsVIAVI["settings"]["NumOne"]["typeofport"]["Port1"],
                          oids["main_alarm"]["alarm_viavi_cnctGE"][alarmname], "255" if alarmname == "VCAIS" else "207")
        time.sleep(1)
        '''Надо доделать, ВИАВИ должен быть подключен к порту и тогда можно менять только и, этого хватит для аварии'''
    elif alarmname == "VCTIM":
        pass
    elif alarmname in ["AUPJE"]:
        asyncio.run(
            snmp_set("1.3.6.1.4.1.5756.3.3.2.12.5.5.2.1.6." + str(oidsSNMP["slots_dict"][block] + f'.1.{portnum}'),
                     Integer(746)))
        VIAVI_set_command(oidsVIAVI["settings"]["NumOne"]["typeofport"]["Port1"],
                          oids["main_alarm"]["alarm_viavi_cnctGE"][alarmname], "INTERNAL")
        time.sleep(2)
    try:
        assert asyncio.run(check_alarm_cnct(block, portnum, vc)) == oids["main_alarm"]["alarm_mib_valueCnctGE"][
            alarmname]
        assert \
            value_parcer_OSMK(get_ssh_value(block, oids["main_alarm"]["cnct_reg_alarm"][block][str(portnum)][str(vc)]))[
                oids["main_alarm"]["alarm_bit_cnctGE"][alarmname]] == "1"
        if alarmname in ["AUAIS", "VCUNEQ", "VCRDI"]:
            VIAVI_set_command(oidsVIAVI["settings"]["NumOne"]["typeofport"]["Port1"],
                              oids["main_alarm"]["alarm_viavi_cnctGE"][alarmname], "OFF")
            time.sleep(1)
    except:
        VIAVI_set_command(oidsVIAVI["settings"]["NumOne"]["typeofport"]["Port1"],
                          oids["main_alarm"]["alarm_viavi_cnctGE"][alarmname], "OFF")
        assert False
