import time
from MainConnectFunc import oidsSNMP
import datetime
import paramiko


def get_ssh_value(slot: str, reg: str) -> str:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(oidsSNMP()['ipaddr'], port=22, username='root', password='')
    ssh.get_transport()
    stdin, stdout, stderr = ssh.exec_command(f'uksmem {hex(int(slot) - 3)[2:]} {reg}')
    result = stdout.read().decode()
    ssh.close()
    return result.strip()

def ssh_reload():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    max_retries = 2
    for attempt in range(max_retries):
        try:
            # Пытаемся подключиться
            ssh.connect("192.168.125.46", port=22, username='admin', password='', timeout=15)

            # Если подключились успешно, выполняем команды
            shell = ssh.invoke_shell()
            shell.send('reload\n')
            time.sleep(1)
            shell.send('y\n')
            ssh.close()
            return  #

        except Exception as e:
            logging.error(f"Ошибка на попытке {attempt + 1}: {str(e)}")
            print(f"\n[!] Сбой SSH на попытке {attempt + 1}. Тип ошибки: {type(e).__name__}")
            print(f"[!] Текст ошибки: {e}")

            if attempt < max_retries - 1:
                wait_time = 3
                print(f"[#] Ждем {wait_time} сек. и пробуем снова...")
                time.sleep(wait_time)
            else:
                print("[!!!] Все попытки подключения исчерпаны.")
                raise e


''' Получение информации о количестве используемых файловых дескриторов'''


def get_sock_value(ip):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, port=22, username='root', password='')
    ssh.get_transport()
    stdin, stdout, stderr = ssh.exec_command(f'cat /proc/sys/fs/file-nr')
    result = stdout.read().decode()
    ssh.close()
    return f"{datetime.datetime.now()} - {result}"


def insert_batch(ssh, db_user, db_name, start_id, batch_size):
    try:
        # values = ", ".join(
        #     [f"({i}, '8.8.8.8', 'sadmin')" for i in range(start_id, start_id + batch_size)])
        value = values = ", ".join([
            f"({i}, '2025-03-07 09:12:15.514460', '192.168.72.50', 'admin', 'read','pass', 'snmp', 'testObj', 'stSubrack', '1', '3', '','','','',1,2,3, '', '',5,6,'','','','','',7,8,9)"
            for i in range(start_id, start_id + batch_size)])
        insert_query = f'''
            INSERT INTO hw_auditmodel (id, date_and_time, address, "user", ro_rw, res, op, obj_name, card_type, card_version, slot_number, pp_name, pp_type, vc4_name, cp_name, index_k, index_l, index_m, value, val_card_type, val_card_version, val_slot_number, val_pp_name, val_pp_type, val_vc4_name, val_cp_name, val_cp_type, val_index_k, val_index_l, val_index_m
) 
            VALUES {values};
        '''
        escaped_insert_query = insert_query.replace("'", "'\\''")
        insert_command = f"psql -U {db_user} -d {db_name} -c '{escaped_insert_query}'"
        stdin, stdout, stderr = ssh.exec_command(insert_command)
        errors = stderr.read().decode()
        if errors:
            return f"Ошибка при вставке пакета {start_id}-{start_id + batch_size - 1}: {errors}"
        else:
            return f"Пакет {start_id}-{start_id + batch_size - 1} успешно вставлен."
    except Exception as e:
        return f"Ошибка при вставке пакета {start_id}-{start_id + batch_size - 1}: {str(e)}"


def bd_alarm_get(alarmname, oid):
    host = oidsSNMP()['ipaddr']
    port = 22
    username = "root"
    password = ""
    db_user = "postgres"
    db_name = "hw_alarm"
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port, username, password)
    try:
        escaped_insert_query = f"SELECT alarmname, soe_alias FROM public.hw_alarm WHERE timeend is NULL and soe_alias LIKE '%{oid}%' and alarmname LIKE '%{alarmname}%' ORDER by timebegin DESC LIMIT 10;"
        insert_command = f"psql -U {db_user} -d {db_name} -c \"{escaped_insert_query}\""
        stdin, stdout, stderr = ssh.exec_command(insert_command)
        out = stdout.read().decode().strip().split('\n')
        indexes_to_remove = [0, 1, -1]
        for index in sorted(indexes_to_remove, reverse=True):
            del out[index]
        return [val.replace(' ', '') for val in out]
    finally:
        ssh.close()


def insert_million_rows():
    host = "192.168.120.88"
    port = 22
    username = "root"
    password = ""

    db_user = "postgres"
    db_name = "hw_alarm"

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port, username, password)

    try:
        # Размер пакета (количество строк за один запрос)
        batch_size = 250
        total_rows = 1000000000  # Общее количество строк для вставки
        start_id = 100000  # Начальное значение id

        while start_id <= total_rows:
            values = ", ".join(
                [f"({i}, '8.8.8.8', 'sadmin')" for i in range(start_id, start_id + batch_size)])
            insert_query = f'''
                INSERT INTO hw_auditmodel (id, address, "user") 
                VALUES {values};
            '''
            # Экранирование SQL-запроса для передачи в shell
            escaped_insert_query = insert_query.replace("'", "'\\''")
            insert_command = f"psql -U {db_user} -d {db_name} -c '{escaped_insert_query}'"

            stdin, stdout, stderr = ssh.exec_command(insert_command)
            errors = stderr.read().decode()
            if errors:
                print(f"Ошибка при вставке пакета {start_id}-{start_id + batch_size - 1}: {errors}")
                break
            else:
                print(f"Пакет {start_id}-{start_id + batch_size - 1} успешно вставлен.")

            # Увеличение start_id для следующего пакета
            start_id += batch_size

    finally:
        ssh.close()
