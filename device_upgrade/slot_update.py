from MainConnectFunc import ssh_exec_commands
from MainConnectFunc import oidsSNMP
from concurrent.futures import ThreadPoolExecutor
import time

OIDS_SNMP = oidsSNMP()
commandsBlockUPD = {"KC": "tftp://192.168.120.199/uks2/08.st/KS_update_GU.sign.zip",
                    "STM-1": "tftp://192.168.120.199/uks2/08.st/STM1_M_U_GU.sign.zip",
                    "STM-4": "tftp://192.168.120.199/uks2/08.st/STM4_V2_U_GU.sign.zip",
                    "STM-16": "tftp://192.168.120.199/uks2/08.st/STM16_V2_U_GU.sign.zip",
                    "21E1": "tftp://192.168.120.199/uks2/06.st/ocmk_21e.sign.bin",
                    "KC-M12": "tftp://192.168.120.199/uks2/08.st/KS-M12_update_GU.sign.zip",
                    "STM-1/4": "tftp://192.168.120.199/uks2/08.st/STM14_M_U_GU.sign.zip",
                    "STM-16M": "tftp://192.168.120.199/uks2/08.st/STM16M_UPDATE_GU.sign.zip",
                    "STM-64M": "tftp://192.168.120.199/uks2/08.st/STM64_UPDATE_GU.sign.zip",
                    "63E1M": "tftp://192.168.120.199/uks2/08.st/63E1M_UPDATE_GU.sign.zip",
                    "Eth100M": "tftp://192.168.120.199/uks2/08.st/ETH_100M_v5_GU.sign.zip",
                    "Eth1000M": "tftp://192.168.120.199/uks2/08.st/ETH1000M_GU.sign.zip"}

imageOSMK = "tftp://192.168.120.199/uks2/08.st/osmk-08.3385.sign.bin"
imageOSMK_M = "tftp://192.168.120.199/uks2/08.st/osmkm-08.3385.sign.bin"

imageOSMK_current = "tftp://192.168.120.11/images/osmk/uksv2/osmk-image-rs0"
imageOSMK_M_current = "tftp://192.168.120.11/images/osmk/uksv2/osmkm-image-rs0"


def image_update_by_dev(version):
    name = OIDS_SNMP.get("name")
    command = None
    if name == "OSM-KMv3":
        if version == "current":
            command = f"copy {imageOSMK_M_current} system-image"
        elif version == "archive":
            command = f"copy {imageOSMK_M} system-image"
    elif name == "OSM-Kv7":
        if version == "Current":
            command = f"copy {imageOSMK_current} system-image"
        elif version == "archive":
            command = f"copy {imageOSMK} system-image"
    return command


def block_update_by_dev(version, block):
    blocks = [block] if isinstance(block, str) else (block or [])
    commands_to_run = []
    for part_block in blocks:
        try:
            slot, block_name = [item.strip() for item in part_block.split(":", 1)]
            target = "all" if version == "all" else slot
            if block_name in commandsBlockUPD:
                command = f"copy {commandsBlockUPD[block_name]} {target} clear yes restart yes full yes"
                commands_to_run.append(command)
        except Exception as e:
            print(f"Error parsing: {e}")
    return list(dict.fromkeys(commands_to_run))
