import time
from MainConnectFunc import oidsSNMP, oids
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
        # escaped_insert_query = f"SELECT * FROM public.hw_auditmodel DESC LIMIT 10;"
        insert_command = f"psql -U {db_user} -d {db_name} -c \"{escaped_insert_query}\""
        stdin, stdout, stderr = ssh.exec_command(insert_command)
        out = stdout.read().decode().strip().split('\n')
        indexes_to_remove = [0, 1, -1]
        for index in sorted(indexes_to_remove, reverse=True):
            del out[index]
        return [val.replace(' ', '') for val in out]
    finally:
        ssh.close()



''' ДЛЯ ПЕРЕСЕЧЕНИЯ ПОРОГА ВЫСТАВАЛЯТЬ SEQUENCE 
su - postgres -c "psql -d hw_alarm"
SELECT * FROM hw_auditmodel_id_seq;
\d hw_auditmodel_id_seq                        --------> убедиться что cycle - yes.
SELECT setval('hw_auditmodel_id_seq', 2147483647);
'''


def insert_clean():
    host = "192.168.72.70"
    port = 22
    username = "root"
    password = ""
    db_name = "hw_alarm"
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(host, port, username, password)

        batch_size = 5
        count_to_insert = 500
        start_id = 2147483600

        current_id = start_id
        while current_id < start_id + count_to_insert:
            next_batch = min(current_id + batch_size, start_id + count_to_insert)

            values = ", ".join(
                [f"({i}, '8.8.8.8', 'sadmin')" for i in range(current_id, next_batch)]
            )
            sql_query = f"INSERT INTO public.hw_auditmodel (id, address, \"user\") VALUES {values};"
            cmd = f'su - postgres -c "psql -d {db_name}" <<EOF\n{sql_query}\nEOF\n'

            stdin, stdout, stderr = ssh.exec_command(cmd)

            out = stdout.read().decode()
            err = stderr.read().decode()

            if "INSERT" in out:
                print(f"Успешно вставлен пакет: {current_id}-{next_batch - 1}")
            else:
                print(f"Ошибка на пакете {current_id}: {err}")
                break

            current_id = next_batch
        print("\nПроверка итогового количества:")
        _, stdout, _ = ssh.exec_command(
            f"su - postgres -c \"psql -d {db_name} -t -c 'SELECT count(*) FROM public.hw_auditmodel WHERE id >= {start_id};'\"")
        print(f"Записей в базе: {stdout.read().decode().strip()}")

    finally:
        ssh.close()
