import json
import telnetlib
import time


def oids():
    with open("../OIDstatusNEW.json", "r") as jsonslot:
        oid = json.load(jsonslot)
        return oid


def mainfunc(reg, blk, IPaddr1):
    tn = telnetlib.Telnet(IPaddr1)
    tn.read_until(b'login:').decode('utf-8')
    time.sleep(0.2)
    tn.write(b'root' + b'\n')
    time.sleep(0.2)
    slotread = f'stateosmk mem {str(hex(int(oids()["OSMKv6"]["slots_dict"][blk]) - 3)[-1])} {reg}'
    tn.write(bytes(slotread, 'utf-8') + b'\n')
    time.sleep(1.5)
    verobj = (tn.read_very_eager().decode('utf-8')).split()
    register = verobj[-2]
    return register


def connectTelnet(IPaddr):
    slots_dict = {}
    tn = telnetlib.Telnet(IPaddr)
    tn.read_until(b'login:').decode('utf-8')
    time.sleep(1)
    tn.write(b'admin' + b'\n')
    time.sleep(1)
    tn.write(b'\n')
    time.sleep(1)
    tn.write(b'show slots' + b'\n')
    time.sleep(2)
    slots = (tn.read_very_eager().decode('utf-8')).split()
    for i in range(len(slots)):
        if slots[i].isdigit() and slots[i + 1] != '|':
            value = slots[i]
            key = slots[i + 1]
            if 'KC' in slots_dict and key[1:] == 'KC':
                key += 'p'
            slots_dict[key[1:]] = value
    for i in slots_dict:
        if slots_dict[i][-2] == '0':
            slots_dict[i] = slots_dict[i][-1]
    with open('../OIDstatusNEW.json') as oid:
        data = json.load(oid)
    data["OSMKv6"]["ipaddr"] = IPaddr
    data["OSMKv6"]["slots_dict"] = slots_dict
    with open('../OIDstatusNEW.json', 'w') as oid:
        json.dump(data, oid, ensure_ascii=False, indent=4)
    return slots_dict


def connect_telnetSMD(ipaddr):
    slots_dict = {}
    tn = telnetlib.Telnet(ipaddr)
    time.sleep(1)
    tn.read_very_eager().decode('utf-8').split()
    time.sleep(1)
    tn.write(b'ver' + b'\r')
    time.sleep(1)
    slots = (tn.read_very_eager().decode('utf-8')).split()
    for i in range(len(slots)):
        if slots[i].isdigit() and slots[i + 1] != '|':
            value = slots[i]
            key = slots[i + 1]
            if 'KS_SS' in slots_dict and key[1:] == 'KS_SS':
                key += 'p'
            if "STM" in key[1:]:
                key = key.replace("M", "M-")
            slots_dict[key[1:]] = value
    with open('../OIDstatusNEW.json') as oid:
        data = json.load(oid)
    data["SMD"]["ipaddr"] = ipaddr
    data["SMD"]["slots_dict"] = slots_dict
    with open('../OIDstatusNEW.json', 'w') as oid:
        json.dump(data, oid, ensure_ascii=False, indent=4)
    trap_host()
    return slots_dict


def mainfuncOSMKv4(reg, blk):
    tn = telnetlib.Telnet(oids()["SMD"]["ipaddr"])
    tn.read_very_eager().decode('utf-8').split()
    slotread = f'read {hex(int(oids()["SMD"]["slots_dict"][blk]))[2:]} {reg}'
    tn.write(bytes(slotread, 'utf-8') + b'\r')
    time.sleep(0.5)
    verobj = (tn.read_very_eager().decode('utf-8')).split()
    register = hex(int(verobj[-2], base=2))[2:]
    # register = register.replace("b", "")
    return register


def trap_host():
    host = get_trap_agent_address()
    tn = telnetlib.Telnet(oids()["SMD"]["ipaddr"])
    tn.read_very_eager().decode('utf-8').split()
    trapset = f'trap 1 {host} 1163 on'
    time.sleep(1)
    tn.write(bytes(trapset, 'utf-8') + b'\r')
