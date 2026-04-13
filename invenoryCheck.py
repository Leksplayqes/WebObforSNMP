import asyncio
import time
from MainConnectFunc import snmp_getBulk, snmp_get
from snmpsubsystem import ProxyController
import datetime
devices = {"192.168.111.61": "Osmk", "192.168.111.62": "Osmk", "192.168.111.63": "Osmkm", "192.168.111.64": "Osmkm",
           "192.168.111.65": "Osmkm",
           "192.168.111.66": "Osmkm",
           "192.168.111.67": "Osmk", "192.168.111.68": "Osmk"}

reference_data = {}


def save_report(ip, name, expected, actual):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("error_report.txt", "a", encoding="utf-8") as f:
        f.write(f"\n{'=' * 60}\n")
        f.write(f"ОШИБКА: {timestamp} | Устройство: {name} ({ip})\n")
        f.write(f"{'-' * 60}\n")

        all_oids = sorted(set(expected.keys()) | set(actual.keys()))
        for oid in all_oids:
            val_exp = expected.get(oid)
            val_act = actual.get(oid)
            if val_exp != val_act:
                f.write(f"OID: {oid}\n")
                f.write(f"  ОЖИДАЛИ: {val_exp}\n")
                f.write(f"  ПОЛУЧИЛИ: {val_act}\n")


async def get_device_data(ctrl, dev_ip, dev_name):
    suffix = 1 if dev_name == "Osmk" else 2
    base_oid = f"1.3.6.1.4.1.5756.3.3.1.{suffix}.9.2.1.1"
    ctrl.start(
        ip=dev_ip,
        username="admin",
        password=f"{dev_name}_{dev_ip.split('.')[-1]}_",
        listen_port=1161
    )

    try:
        await asyncio.sleep(2)
        raw_data = await snmp_getBulk(f".{base_oid}", 15)
        filtered = {k: v for k, v in raw_data.items() if k.startswith(base_oid)}
        return filtered
    finally:
        ctrl.dispose()


async def main_test_loop():
    reference_data = {}
    ctrl = ProxyController()
    print("--- Сбор эталонных значений ---")
    for ip, name in devices.items():
        data = await get_device_data(ctrl, ip, name)
        reference_data[ip] = data
    while True:
        print(f"--- Проверка ({time.strftime('%H:%M:%S')}) ---")
        for ip, name in devices.items():
            current_data = await get_device_data(ctrl, ip, name)

            if current_data != reference_data[ip]:
                print(f"!!! ТЕСТ ПРОВАЛЕН на устройстве {ip} !!!")
                save_report(ip, name, reference_data[ip], current_data)
                for oid, val in reference_data[ip].items():
                    new_val = current_data.get(oid)
                    if val != new_val:
                        print(f"Ошибка в OID {oid}: ожидали {val}, получили {new_val}")
                return

        print("Все сошлось")
        await asyncio.sleep(1800)


if __name__ == "__main__":
    asyncio.run(main_test_loop())
