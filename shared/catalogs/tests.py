"""Catalogs of available pytest nodeids grouped by feature."""
from __future__ import annotations
from MainConnectFunc import oidsSNMP

SYNC_TESTS_CATALOG = {
    "Создание/удаление приоритетов (STM/E1)": "unit_tests/test_syncV7v2.py::test_STM_E1_create_del",
    "Режим QL: выключить": "unit_tests/test_syncV7v2.py::test_QLmodeDOWN",
    "Режим QL: включить": "unit_tests/test_syncV7v2.py::test_QLmodeUP",
    "Создание внешнего источника синхронизации": "unit_tests/test_syncV7v2.py::test_extPortID",
    "Занятие/очистка шины SYNC": "unit_tests/test_syncV7v2.py::test_busSYNC",
    "Установка качества для extPort": "unit_tests/test_syncV7v2.py::test_extPortQL",
    "Конфигурация частоты extPort": "unit_tests/test_syncV7v2.py::test_extPortConf",
    "STM как источник для extPort": "unit_tests/test_syncV7v2.py::test_extSourceID",
    "Статус приоритета (STM)": "unit_tests/test_syncV7v2.py::test_prior_statusSTM",
    "Получение уровня QL на STM-входе": "unit_tests/test_syncV7v2.py::test_QLSTM_get",
    "Передача QL через STM": "unit_tests/test_syncV7v2.py::test_QLSTM_set",
    "Передача QL через Е1": "unit_tests/test_syncV7v2.py::test_QLE1_set",
    "Запись STM как источника выхода": "unit_tests/test_syncV7v2.py::test_STM_extport",
    "Соответствие QL extPort ↔ STM": "unit_tests/test_syncV7v2.py::test_STM_QL_extport",
    "Аварии по порогам QL (блоки)": "unit_tests/test_syncV7v2.py::test_ThresQL_AlarmBlock",
    "Аварии по порогам QL (SETS)": "unit_tests/test_syncV7v2.py::test_ThreshQL_AlarmSETS",
} if oidsSNMP()["name"] != "SMD2v2" else {
    "Создание/удаление приоритетов (STM/E1)": "unit_tests/test_syncSMD2.py::test_STM_E1_create_del",
    "Режим QL: выключить": "unit_tests/test_syncSMD2.py::test_QLmodeDOWN",
    "Режим QL: включить": "unit_tests/test_syncSMD2.py::test_QLmodeUP",
    "Создание внешнего источника синхронизации": "unit_tests/test_syncSMD2.py::test_extPortID",
    "Установка качества для extPort": "unit_tests/test_syncSMD2.py::test_extPortQL",
    "Конфигурация частоты extPort": "unit_tests/test_syncSMD2.py::test_extPortConf",
    "STM как источник для extPort": "unit_tests/test_syncSMD2.py::test_extSourceID",
    "Включение порогов FDEV": "unit_tests/test_syncSMD2.py::test_FDEV_enable",
    "Выключение порогов FDEV": "unit_tests/test_syncSMD2.py::test_FDEV_disable",
    "Важность аварии FDEV": "unit_tests/test_syncSMD2.py::test_FDEV_category",
    "Переключение режима Мбит/МГц": "unit_tests/test_syncSMD2.py::test_clock_ext",
    "Статус приоритета (STM)": "unit_tests/test_syncSMD2.py::test_prior_statusSTM",
    "Получение уровня QL на STM-входе": "unit_tests/test_syncSMD2.py::test_QLSTM_get",
    "Передача QL через STM": "unit_tests/test_syncSMD2.py::test_QLSTM_set",
    "Передача QL через Е1": "unit_tests/test_syncSMD2.py::test_QLE1_set",
    "Запись STM как источника выхода": "unit_tests/test_syncSMD2.py::test_STM_extport",
    "Соответствие QL extPort ↔ STM": "unit_tests/test_syncSMD2.py::test_STM_QL_extport",
    "Аварии по порогам QL (блоки)": "unit_tests/test_syncSMD2.py::test_ThresQL_AlarmBlock",
    "Аварии по порогам QL (SETS)": "unit_tests/test_syncSMD2.py::test_ThreshQL_AlarmSETS",
}

ALARM_TESTS_CATALOG = {
    "Физические аварии STM": "unit_tests/test_alarmV7.py::test_physical_alarmSTM",
    "Аварии VC STM": "unit_tests/test_alarmV7.py::test_connective_alarmSTM",
    "Аварии VC E1": "unit_tests/test_alarmV7.py::test_connective_alarmE1",
    "Аварии VC GE": "unit_tests/test_alarmV7.py::test_connective_alarmGE",
} if oidsSNMP()["name"] != "SMD2v2" else {
    "Физические аварии STM": "unit_tests/test_alarmSMD2.py::test_physical_alarmSTM",
    "Аварии VC STM": "unit_tests/test_alarmSMD2.py::test_connective_alarmSTM",
    "Аварии VC E1": "unit_tests/test_alarmSMD2.py::test_connective_alarmE1",
    "Аварии VC GE": "unit_tests/test_alarmSMD2.py::test_connective_alarmGE"}
STAT_TEST_CATALOG = {"STATISTIC TRUE": "unit_tests/test_alarmV7.py::test_connective_alar", }

COMM_TEST_CATALOG = {"Коммутация VC4": "OsmCommutations/test_commutations.py::test_commutationsVC4",
                     "Коммутация VC12": "OsmCommutations/test_commutations.py::test_commutationsVC12",
                     "Коммутация Е1": "OsmCommutations/test_commutations.py::test_commutationsE1"}

OTHER_TEST_CATALOG = {"Запись BlockCategory": "OsmCategory/test_OSMK_category.py::test_set_block_category",
                      "Сохранение BlockCategory": "OsmCategory/test_OSMK_category.py::test_check_block_category",

                      "Запись SubrackCategory": "OsmCategory/test_OSMK_category.py::test_set_equipment_category",
                      "Сохранение SubrackCategory": "OsmCategory/test_OSMK_category.py::test_check_equipment_category",

                      "Запись SyncCategory": "OsmCategory/test_OSMK_category.py::test_set_sync_category",
                      "Сохранение SyncCategory": "OsmCategory/test_OSMK_category.py::test_check_sync_category",

                      "Запись BlockLabel": "OsmCategory/test_OSMK_category.py::test_set_label",
                      "Сохранение BlockLabel": "OsmCategory/test_OSMK_category.py::test_check_label",

                      "Запись AllMask": "OsmCategory/test_OSMK_category.py::test_set_mask",
                      "Сохранение AllMask": "OsmCategory/test_OSMK_category.py::test_check_mask",

                      "Запись BlockLoop": "OsmCategory/test_OSMK_category.py::test_set_loop",
                      "Сохранение BlockLoop": "OsmCategory/test_OSMK_category.py::test_check_loop",

                      "Запись TraceXX": "OsmCategory/test_OSMK_category.py::test_set_trace",
                      "Сохранение TraceXX": "OsmCategory/test_OSMK_category.py::test_check_trace",
                      }

__all__ = ["SYNC_TESTS_CATALOG", "ALARM_TESTS_CATALOG", "STAT_TEST_CATALOG", "COMM_TEST_CATALOG", "OTHER_TEST_CATALOG"]
