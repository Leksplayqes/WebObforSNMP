import asyncio
import os
import json
import datetime
import time
from typing import Tuple, Dict, Any, Callable, Optional

import paramiko
from scp import SCPClient

# Импорт SNMP-хелперов
from MainConnectFunc import snmp_getBulk, oidsSNMP
from unit_tests.SnmpV7alarm import check_alarmSFP, check_lockSFP

STATE_FILE = "OIDstatusNEW.json"
LOCAL_BASE_PATH = "checkFunctions/LogConf"

# ---------- SSH / SCP ----------
import paramiko


def ssh_exec(ip: str, username: str, password: str, command: str, timeout: int = 10) -> str:
    transport = paramiko.Transport((ip, 22))
    transport.start_client(timeout=timeout)

    def handler(title, instructions, prompts):
        return [password for _ in prompts]

    transport.auth_interactive(username, handler)
    channel = transport.open_session()
    channel.settimeout(timeout)
    channel.get_pty()
    channel.exec_command(command)

    out = b""
    err = b""
    last_data = time.time()
    while True:
        got_any = False
        if channel.recv_ready():
            out += channel.recv(4096)
            got_any = True
            last_data = time.time()
        if channel.recv_stderr_ready():
            err += channel.recv_stderr(4096)
            got_any = True
            last_data = time.time()
        if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
            break
        if not got_any and (time.time() - last_data) > timeout:
            break
        time.sleep(0.05)

    channel.close()
    transport.close()
    output = out.decode("utf-8", errors="replace")
    if err:
        output += "\n[stderr]\n" + err.decode("utf-8", errors="replace")
    return output


def ssh_reload(ip: str, password: str) -> None:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, port=22, username="admin", password=password)
    try:
        shell = ssh.invoke_shell()
        shell.send("reload\n")
        time.sleep(0.5)
        shell.send("y\n")
        time.sleep(0.5)
    finally:
        ssh.close()


def scp_copy_remote_dir(ip: str, username: str, password: str, remote_path: str, local_dir: str) -> str:
    os.makedirs(local_dir, exist_ok=True)
    ssh = paramiko.SSHClient()

    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, port=22, username=username, password=password, timeout=10)

    try:
        with SCPClient(ssh.get_transport()) as scp:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            target = os.path.join(local_dir, f"{os.path.basename(remote_path)}_{ts}")
            os.makedirs(target, exist_ok=True)
            scp.get(remote_path, target, recursive=True)

            return target
    finally:
        ssh.close()


# ---------- SNMP SFP check ----------
def snmp_check_sfp_status_for_stm_slots() -> Tuple[bool, bool]:
    alarms_result = asyncio.run(check_alarmSFP())
    check_result = asyncio.run(check_lockSFP())
    no_alarms = len(set(alarms_result)) <= 1
    no_blocking = len(set(check_result)) <= 1
    return no_alarms, no_blocking


# ---------- Основная функция с циклом итераций ----------
def check_conf(
        ip: str,
        password: str,
        iterations: int = 3,
        delay_between: int = 30,
        progress_cb: Optional[Callable[[int, int, Dict[str, Any], Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "ip": ip,
        "iterations": iterations,
        "started": datetime.datetime.now().isoformat(timespec="seconds"),
        "results": [],
    }
    original_conf = ssh_exec(ip, "admin", password, "show running-config")
    for i in range(1, iterations + 1):
        iter_result: Dict[str, Any] = {
            "iteration": i,
            "start_time": datetime.datetime.now().isoformat(timespec="seconds"),
            "steps": [],
        }
        try:
            # 1. show running-config
            config = ssh_exec(ip, "admin", password, "show running-config")
            iter_result["steps"].append({"get_config": config})
            # 2. SNMP check STM slots
            # no_alarms, no_blocking = snmp_check_sfp_status_for_stm_slots()
            # iter_result["steps"].append(
            #     {
            #         "sfp_check": {
            #             "no_alarms": no_alarms,
            #             "no_blocking": no_blocking,
            #         }
            #     }
            # )
            # if not (no_alarms and no_blocking):
            #     iter_result["status"] = "alarm_detected"
            #     summary["results"].append(iter_result)
            #     if progress_cb:
            #         progress_cb(i, iterations, iter_result, summary)
            #     continue

            # 3. copy configs and logs

            # cfg_dir = scp_copy_remote_dir(ip, "root", "", "/var/volatile/tmp/smd/config", LOCAL_BASE_PATH)
            # log_dir = scp_copy_remote_dir(ip, "root", "", "/var/volatile/log", LOCAL_BASE_PATH)
            # iter_result["steps"].append({"copy": {"config": cfg_dir, "log": log_dir}})

            # 4. reload if config unchanged
            if original_conf == config:
                ssh_reload(ip, password)
                iter_result["steps"].append({"reload": "sent"})
                time.sleep(delay_between)
            else:
                iter_result["steps"].append({"reload": "skipped - config changed"})
                iter_result["status"] = "config_changed"
                summary["results"].append(iter_result)
                if progress_cb:
                    progress_cb(i, iterations, iter_result, summary)
                break

            iter_result["status"] = "ok"
        except Exception as e:
            iter_result["status"] = f"error: {e}"

        iter_result["end_time"] = datetime.datetime.now().isoformat(timespec="seconds")
        summary["results"].append(iter_result)

        if progress_cb:
            progress_cb(i, iterations, iter_result, summary)

    summary["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
    ok_count = sum(1 for r in summary["results"] if r.get("status") == "ok")
    summary["status"] = f"OK {ok_count}/{iterations}"

    return summary


