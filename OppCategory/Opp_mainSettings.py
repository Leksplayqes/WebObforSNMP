import asyncio
import json
import time

import paramiko
from puresnmp import Client, V2C, PyWrapper

with open("OppCategory.json", "r") as jsonblock:
    oid = json.load(jsonblock)


def connect():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(oid["DevSettings"]["IP"], port=22, username='admin', password='')
    shell = ssh.invoke_shell()
    return ssh, shell


def device_reboot():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(oid["DevSettings"]["IP"], port=22, username='admin', password='')
    shell = ssh.invoke_shell()
    shell.send('reload\n')
    time.sleep(1)
    shell.send('y\n')
    ssh.close()
    time.sleep(90)


def cli_set_category(slot, block):
    ssh, shell = connect()
    shell.send(f"slot {slot}\nconf\n")
    for command in oid['CliCategory'][block]:
        time.sleep(0.7)
        shell.send(f"{command} {f'4'.ljust(2) * oid['CliCategory'][block][command]}\n")


def client():
    return PyWrapper(Client(oid["DevSettings"]["IP"], V2C("private")))


async def set_oid_value(client, oid, value):
    await client.set(oid, value)


async def get_oid_value(client, oid):
    return await client.get(oid)


async def get_blockList():
    blockDict = {"10": "MX210Gv1", "1": "MVPv1", "0": "Free", "4": "MKv1", "11": "MX100GCv1", "16": "TP410Gv1", "15": "TP510Gv1",
                 "14": "MV2Mv1", "3": "MASv1", "12": "OUv1", "13": "ROADMv1", "5": "DWDM40v1", "9": "DWDM401v1"}
    blockList = {}
    for slot in range(1, 14):
        client_host = client()
        value = await get_oid_value(client_host, f".1.3.6.1.4.1.5756.10.1.4.1.2.1.3.{slot}")
        blockList[blockDict[str(value)]] = slot
    with open('OppCategory.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    data["DevSettings"]["BlockList"] = blockList
    with open('OppCategory.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    return blockList

# print(asyncio.run(get_blockList()))