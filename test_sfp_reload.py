import asyncio
import datetime
import pytest
import os
from MainConnectFunc import *
from MainConnectFunc import oids as get_oids
from MainConnectFunc import oidsSNMP as get_oids_snmp
from MainConnectFunc import oidsVIAVI as get_viavi_oids
from unit_tests.SnmpV7alarm import check_alarmSFP, check_lockSFP, setSFP_Mode
from scp import SCPClient
import pytest_asyncio
OIDS_SNMP = get_oids_snmp()
OIDS = get_oids()
OIDS_VIAVI = get_viavi_oids()
SLOTS_DICT = OIDS_SNMP.get("slots_dict", {})

STATE_FILE = "OIDstatusNEW.json"
LOCAL_BASE_PATH = "checkFunctions/LogConf"


async def get_sfp_alarmStatus():
    alarms_result = await check_alarmSFP()
    check_result = await check_lockSFP()
    no_alarms = not any(code in alarms_result for code in ["1", "2", "4", "8"])
    no_blocking = len(set(check_result)) <= 1
    return no_alarms, no_blocking


async def scp_copy_remote_dir(remote_path: str, local_dir: str) -> str:
    ip = OIDS_SNMP['ipaddr']
    os.makedirs(local_dir, exist_ok=True)
    ssh = paramiko.SSHClient()

    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, port=22, username="root", password="", timeout=10)

    try:
        with SCPClient(ssh.get_transport()) as scp:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            target = os.path.join(local_dir, f"{os.path.basename(remote_path)}_{ts}")
            os.makedirs(target, exist_ok=True)
            scp.get(remote_path, target, recursive=True)

            return target
    finally:
        ssh.close()

async def ssh_reload() -> None:
    ip, password = OIDS_SNMP['ipaddr'], OIDS_SNMP["pass"]
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, port=22, username="admin", password=password, timeout=10)

    chan = ssh.invoke_shell()
    await asyncio.sleep(1)

    chan.send("reload\n")
    await asyncio.sleep(1)
    chan.send("y\n")
    await asyncio.sleep(0.5)
    ssh.close()


def ssh_exec_commands(commands: list, timeout_seconds: int = 1200):
    """
    Выполняет команды и стримит чистый вывод устройства в Streamlit.
    Игнорирует промежуточные решетки # и фильтрует эхо команд.
    """
    transport = None
    try:
        # 1. Подключение
        transport = paramiko.Transport((oidsSNMP()['ipaddr'], 22))
        transport.set_keepalive(30)
        transport.start_client(timeout=15)

        def handler(title, instructions, prompt_list):
            return [oidsSNMP()['pass']] * len(prompt_list)

        transport.auth_interactive("admin", handler)
        channel = transport.open_session()
        channel.get_pty(width=200)  # Широкий экран, чтобы строки не рвались
        channel.invoke_shell()

        # 2. Определение Hostname (один раз при входе)
        time.sleep(2)
        initial_data = ""
        if channel.recv_ready():
            initial_data = channel.recv(9999).decode('utf-8', errors='ignore')

        # Находим имя устройства, например 'osmkm' из 'osmkm#'
        match = re.search(r'([\w\.\-]+)#', initial_data)
        hostname = match.group(1) if match else "osmkm"

        # СТРОГИЙ ПАТТЕРН ПРОМПТА: Начало строки + Имя + # + конец данных
        # Это исключит срабатывание на прогресс-бары #######
        prompt_re = re.compile(rf"^\r?{re.escape(hostname)}(?:\([\w\-]+\))?#\s*$")

        # 3. Последовательное выполнение
        for cmd in commands:
            clean_cmd = cmd.strip()
            channel.send(f"{clean_cmd}\n")

            cmd_output = ""
            start_time = time.time()

            while True:
                if channel.recv_ready():
                    chunk = channel.recv(8192).decode('utf-8', errors='ignore')

                    # Фильтруем "эхо" (повтор команды устройством) и мусор
                    display_chunk = chunk.replace(clean_cmd, "")
                    display_chunk = display_chunk.replace("% Unknown command.", "")

                    if display_chunk:
                        yield display_chunk  # Отправляем в Streamlit

                    cmd_output += chunk

                    # ПРОВЕРКА ЗАВЕРШЕНИЯ:
                    # Разбираем накопленный текст на строки и смотрим только на ПОСЛЕДНЮЮ
                    lines = cmd_output.strip().splitlines()
                    if lines:
                        last_line = lines[-1].strip()
                        # Если последняя строка — это в точности наш промпт, выходим из цикла
                        if prompt_re.match(last_line):
                            break

                # Защита от зависания (по умолчанию 20 минут)
                if time.time() - start_time > timeout_seconds:
                    yield "\n[TIMEOUT: Процесс прерван по времени]\n"
                    break

                time.sleep(0.1)

    except Exception as e:
        yield f"\n[SSH ERROR]: {str(e)}\n"
    finally:
        if transport:
            transport.close()


@pytest_asyncio.fixture(scope="module")
async def get_original_conf():
    await setSFP_Mode()
    return await ssh_execute_command("show running-config")


@pytest.mark.asyncio
@pytest.mark.parametrize("iteration", range(500))
async def test_check_config(get_original_conf, iteration):
    # config = await ssh_execute_command("show running-config")
    no_alarms, no_blocking = await get_sfp_alarmStatus()
    if not (no_alarms and no_blocking):
        await scp_copy_remote_dir("/var/volatile/tmp/osmkm/config", LOCAL_BASE_PATH)
        pytest.fail("Alarms or dislock detected!")
    await ssh_reload()
    time.sleep(130)
    # if get_original_conf == config:
    #     await ssh_reload()
    #     time.sleep(150)
    # else:
    #     await scp_copy_remote_dir("/var/volatile/tmp/osmkm/config", LOCAL_BASE_PATH)
    #     pytest.fail("Config changed during test")
