import datetime
import time

import paramiko


def fpga_reload(*, ip: str, password: str, slot: int = 9, max_attempts: int = 1000, wait_seconds: int = 35):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, port=22, username="admin", password=password)
    _, stdout, _ = ssh.exec_command(f"state slot {slot}")
    success_marker = stdout.read().decode()
    entries = []

    try:
        for attempt in range(1, max_attempts + 1):
            ssh.exec_command(f"fpga-reload {slot}")
            time.sleep(wait_seconds)
            _, stdout, _ = ssh.exec_command(f"state slot {slot}")
            result = stdout.read().decode()
            success = success_marker in result
            entries.append(
                {
                    "attempt": attempt,
                    "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
                    "success": success,
                    "output": result.strip(),
                }
            )
            if not success:
                break
        return {"attempts": len(entries), "success": bool(entries and entries[-1]["success"]), "entries": entries}
    finally:
        ssh.close()


if __name__ == "__main__":
    from getpass import getpass

    ip = input("Device IP: ")
    slot = int(input("Slot: ") or "9")
    fpga_reload(ip=ip, password="", slot=slot, max_attempts=3)
