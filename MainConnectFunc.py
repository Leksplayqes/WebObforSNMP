import asyncio
import json
import os
import subprocess
import time
import paramiko
import re
import sys
import os
from pysnmp.hlapi.asyncio import (bulk_cmd, SnmpEngine, UsmUserData, UdpTransportTarget, ContextData, ObjectType,
                                  get_cmd, set_cmd,
                                  ObjectIdentity, OctetString)


def oids():
    with open(r"C:\Users\mikhailov_gs.SUPERTEL\PycharmProjects\STwebTestingNew\OIDstatusNEW.json", "r") as jsonblock:
        oid = json.load(jsonblock)
        if oid["CurrentEQ"]["name"] != "-":
            oids = oid[oid["CurrentEQ"]["name"]]
            return oids
        else:
            pass



def oidsSNMP():
    snapshot_raw = os.getenv("OSMK_CURRENT_EQ_SNAPSHOT")
    if snapshot_raw:
        try:
            snapshot = json.loads(snapshot_raw)
            if isinstance(snapshot, dict):
                return snapshot
        except Exception:
            pass
    with open(r"C:\Users\mikhailov_gs.SUPERTEL\PycharmProjects\STwebTestingNew\OIDstatusNEW.json", "r") as jsonblock:
        oid = json.load(jsonblock)
        oidsSNMP = oid["CurrentEQ"]
        return oidsSNMP


def find_KS():
    for i in oidsSNMP()["slots_dict"]:
        if "KC" in oidsSNMP()["slots_dict"][i]:
            return i


def oidsVIAVI():
    with open(r"C:\Users\mikhailov_gs.SUPERTEL\PycharmProjects\STwebTestingNew\OIDstatusNEW.json", "r") as jsonblock:
        oid = json.load(jsonblock)
        oidsVIAVI = oid["VIAVIcontrol"]
        return oidsVIAVI


file_lock = asyncio.Lock()


async def json_input(key_path, new_value):
    async with file_lock:
        filename = 'OIDstatusNEW.json'

        # Читаем
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)


        current = data
        for i, key in enumerate(key_path):
            if i < len(key_path) - 1:
                current = current[key]
            else:
                current[key] = new_value

        # Пишем
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)


def run_tunnel(ip, password):
    command = f"ncat -uk -l -c \"exec sshpass -p '{password}' ssh admin@{ip} -p 22 -s snmp\" 127.0.0.1 1161"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return process


def close_tunnel():
    command = f"kill `lsof -t -i :1161`"
    subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


async def multi_snmp_get(oids: list):
    object_types = [ObjectType(ObjectIdentity(oid)) for oid in oids]
    error_indication, error_status, error_index, var_binds = await get_cmd(
        SnmpEngine(), UsmUserData("admin"),
        await UdpTransportTarget.create(("localhost", oidsSNMP()["snmp_port"]), timeout=0.5, retries=1),
        ContextData(),
        *object_types)
    return [str(var_bind[1]) for var_bind in var_binds]


async def snmp_set_bulk(oid_value_pairs, community="admin"):
    object_types = [ObjectType(ObjectIdentity(oid), value) for oid, value in oid_value_pairs]
    error_indication, error_status, error_index, var_binds = await set_cmd(
        SnmpEngine(),
        UsmUserData(community),
        await UdpTransportTarget.create(("localhost", oidsSNMP()["snmp_port"]), timeout=0.5, retries=1),
        ContextData(),
        *object_types)
    return [str(var_bind[1]) if var_bind[1] else None
            for var_bind in var_binds]


async def snmp_set(oid, value):
    try:
        error_indication, error_status, error_index, var_binds = await set_cmd(
            SnmpEngine(),
            UsmUserData("admin"),
            await UdpTransportTarget.create(("localhost", oidsSNMP()["snmp_port"])),
            ContextData(),
            ObjectType(ObjectIdentity(oid), value)
        )
        if error_indication:
            print(f"Ошибка соединения: {error_indication}")
        elif error_status:
            print(f"Ошибка SNMP: {error_status.prettyPrint()}")
        else:
            for var_bind in var_binds:
                return var_bind[1]
    except Exception as e:
        print(f"Критическая ошибка: {e}")


async def snmp_get(oid):
    error_indication, error_status, error_index, var_binds = \
        await get_cmd(SnmpEngine(), UsmUserData("admin"),
                      await UdpTransportTarget.create(("localhost", int(oidsSNMP()["snmp_port"])), timeout=0.5,
                                                      retries=1),
                      ContextData(), ObjectType(ObjectIdentity(oid)))
    for value in var_binds:
        return value[1]


async def snmp_getBulk(oid: str, max_repetitions: int):
    base = oid.rstrip('.')
    result = {}

    error_indication, error_status, error_index, var_binds = await bulk_cmd(
        SnmpEngine(),
        UsmUserData("admin"),
        await UdpTransportTarget.create(("localhost", oidsSNMP()["snmp_port"])),
        ContextData(),
        0, max_repetitions,
        ObjectType(ObjectIdentity(base)),
        lexicographicMode=False
    )
    for row in var_binds:
        row = (str(row).split())
        result[f'1.3.6.1.4.1.{row[0][24:]}'] = row[2]
    return result


async def snmp_multiset(oid_value_pairs):
    CHUNK_SIZE = 21
    all_var_binds = []
    for i in range(0, len(oid_value_pairs), CHUNK_SIZE):
        chunk = oid_value_pairs[i: i + CHUNK_SIZE]

        object_types = []
        for oid, value in chunk:
            obj_id = ObjectIdentity(oid)
            object_types.append(ObjectType(obj_id, value))
        error_indication, error_status, error_index, var_binds = await set_cmd(
            SnmpEngine(),
            UsmUserData("admin"),
            await UdpTransportTarget.create(("localhost", oidsSNMP()["snmp_port"]), timeout=2, retries=2),
            ContextData(),
            *object_types
        )
        if error_indication:
            print(f"Connection Error (chunk {i // CHUNK_SIZE + 1}): {error_indication}")
            return all_var_binds
        if error_status:
            print(f"SNMP Error: {error_status.prettyPrint()} at {error_index} in chunk {i // CHUNK_SIZE + 1}")
            return all_var_binds

        all_var_binds.extend(var_binds)
    return all_var_binds


async def get_device_info():
    try:
        device_info = await snmp_get("1.3.6.1.2.1.1.1.0")
        name = str(device_info).split()[0]
        version = '7' if name in ['OSM-K', 'P-317S'] else ('2' if name in ["SMD2"] else '3')
        if device_info:
            await json_input(["CurrentEQ", "name"], f"{name}v{version}")
        else:
            return False
        return f"{name}v{version}"
    except Exception as e:
        print(f"Ошибка получения информации об устройстве: {e}")
        return False


async def equpimentV7():
    idReal = await snmp_getBulk("1.3.6.1.4.1.5756.1.220.1.1.2", 16 if oidsSNMP()["name"] == "SMD2v2" else 12)
    noNullIdReal = {slot.split('.')[-1]: block for slot, block in idReal.items() if
                    block != '1.3.6.1.4.1.5756.1.202.0' and block != '1.3.6.1.4.1.5756.1.207.0'}
    for k in noNullIdReal:
        for j in oids()["blockOID"]['statusOID']:
            if noNullIdReal[k] in oids()["blockOID"]['statusOID'][j]:
                noNullIdReal[k] = j
    await json_input(["CurrentEQ", "slots_dict"], noNullIdReal)
    return noNullIdReal


''' Делает из hex полноразмерный bin'''


def hex_to_bin(hex_str):
    return format(int(hex_str, 16), f"0{len(hex_str) * 4}b")


def get_full_ssh_output(command) -> str:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    timeout = 1

    try:
        ssh.connect(oidsSNMP()['ipaddr'], port=22, username='root', password='', timeout=5)
        transport = ssh.get_transport()
        channel = transport.open_session()
        channel.settimeout(timeout)

        channel.exec_command(command)

        output = b""
        while True:
            if channel.recv_ready():
                data = channel.recv(8192)
                if not data:
                    break
                output += data

            if channel.exit_status_ready() and not channel.recv_ready():
                break
            time.sleep(0.1)

        result = output.decode('utf-8', errors='ignore')
        return result.strip()

    finally:
        ssh.close()


def ssh_exec_commands(commands: list, timeout_seconds: int = 900):
    transport = None
    try:
        transport = paramiko.Transport((oidsSNMP()['ipaddr'], 22))
        transport.set_keepalive(30)
        transport.start_client(timeout=15)

        def handler(title, instructions, prompt_list):
            return [oidsSNMP()['pass']] * len(prompt_list)

        transport.auth_interactive("admin", handler)

        channel = transport.open_session()
        channel.get_pty()
        channel.invoke_shell()

        time.sleep(2)
        if channel.recv_ready():
            channel.recv(9999)

        channel.send("\n")
        time.sleep(0.5)
        hostname = "osmk"
        if channel.recv_ready():
            raw_data = channel.recv(4096).decode('utf-8', errors='ignore')
            match = re.search(r'([\w\.\-]+)#', raw_data)
            if match:
                hostname = match.group(1)

        prompt_pattern = rf"(?m)^{re.escape(hostname)}(\([\w\-]+\))?#\s*$"

        for cmd in commands:
            clean_cmd = cmd.strip()
            channel.send(f"{clean_cmd}\n")

            cmd_output = ""
            start_time = time.time()

            while True:
                if channel.recv_ready():
                    chunk = channel.recv(4096).decode('utf-8', errors='ignore')
                    if chunk.strip() == clean_cmd:
                        cmd_output += chunk
                        continue
                    yield chunk
                    cmd_output += chunk
                    if "Are you sure?" in chunk or "update the system image?" in chunk:
                        channel.send("y\n")
                        yield "y\n"
                        start_time = time.time()
                        continue
                    if re.search(prompt_pattern, cmd_output):
                        break
                if time.time() - start_time > timeout_seconds:
                    if hostname + "#" in cmd_output:
                        break
                    yield f"\n[TIMEOUT: {clean_cmd}]\n"
                    break

                time.sleep(0.1)

    except Exception as e:
        yield f"\n[SSH ERROR]: {str(e)}\n"
    finally:
        if transport:
            transport.close()


# ====================== ПРОЧЕЕ ======================

def value_parser_OSMK(value: str) -> str:
    try:
        return bin(int(value, 16))[2:].zfill(16)
    except ValueError:
        return "0" * 16
