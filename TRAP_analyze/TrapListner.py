import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import ifaddr
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import engine, config
from pysnmp.entity.rfc3413 import ntfrcv

TEXT_LOG_FILENAME = "received_traps.log"
JSON_LOG_FILENAME = "received_traps.jsonl"
DESCR_FILENAME = "TrapDescript.json"

SYSUPTIME_OID = "1.3.6.1.2.1.1.3.0"
SNMPTRAPOID_OID = "1.3.6.1.6.3.1.1.4.1.0"


def get_trap_agent_address() -> Optional[str]:
    iplist: List[str] = []
    adapt = ifaddr.get_adapters()
    for ad in adapt:
        if hasattr(ad, "ips"):
            for ip in ad.ips:
                ip = str(ip)
                if "Ethernet 3" in ip and ":" not in ip:
                    trap_ip = ip.split()[0][7:-2]
                    iplist.append(trap_ip)
    return iplist[0] if iplist else None


def configure_snmp_engine(snmpEngine, TrapAgentAddress: str, Port: int) -> None:
    config.add_transport(
        snmpEngine,
        udp.DOMAIN_NAME + (1,),
        udp.UdpTransport().open_server_mode((TrapAgentAddress, Port)),
    )
    config.add_v1_system(snmpEngine, "public", "public")


def _load_descr() -> Dict[str, Any]:
    with open(DESCR_FILENAME, "r", encoding="utf-8") as f:
        return json.load(f)


def _append_jsonl(record: Dict[str, Any]) -> None:
    try:
        with open(JSON_LOG_FILENAME, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _extract_transport_src(snmpEngine, stateReference) -> Tuple[Optional[str], Optional[int]]:
    try:
        info = snmpEngine.msgAndPduDsp.getTransportInfo()
        if isinstance(info, tuple) and len(info) >= 2:
            addr = info[1]
            if isinstance(addr, tuple) and len(addr) >= 2:
                return str(addr[0]), int(addr[1])
    except Exception:
        pass
    return None, None


def _build_processed_lines(varBinds, OIDdescr: Dict[str, Any]) -> List[str]:
    processed_lines: List[str] = []

    for name, val in varBinds:
        name_str = name.prettyPrint()
        val_str = val.prettyPrint()
        processed = False

        for device in OIDdescr:
            for service in OIDdescr[device]:
                for value in OIDdescr[device][service]:
                    for descr in OIDdescr[device][service][value]:
                        if descr in name_str:
                            final_line = (
                                f"{value}"
                                f"{OIDdescr[device][service][value][descr]}."
                                f"{name_str.replace(descr, '')}"
                                f" = {val_str}"
                            )
                            processed_lines.append(final_line)
                            processed = True
                            break
                    if processed:
                        break
                if processed:
                    break
            if processed:
                break

        if not processed:
            processed_lines.append(f"{name_str} = {val_str}")

    return processed_lines


def _extract_key_fields(varBinds) -> Dict[str, Any]:
    sys_uptime = None
    trap_oid = None

    for name, val in varBinds:
        oid = name.prettyPrint()
        v = val.prettyPrint()
        if oid == SYSUPTIME_OID:
            sys_uptime = v
        elif oid == SNMPTRAPOID_OID:
            trap_oid = v
    return {"sys_uptime": sys_uptime, "snmp_trap_oid": trap_oid}


def trap_callback(snmpEngine, stateReference, contextEngineId, contextName, varBinds, cbCtx):
    receive = "Received new Trap message"
    now = datetime.datetime.now()

    header = f"{now.time()} {receive}"
    logging.info(header)

    try:
        OIDdescr = _load_descr()
    except Exception as exc:
        OIDdescr = {}
        logging.error(f"Failed to load {DESCR_FILENAME}: {exc}")

    processed_lines = _build_processed_lines(varBinds, OIDdescr)
    log_processed_lines = []
    for name, val in varBinds:
        name_str = name.prettyPrint()
        val_str = val.prettyPrint()
        log_processed_lines.append(f"{name_str} = {val_str}")

    for line in log_processed_lines:
        logging.info(line)

    vb_struct = [{"oid": n.prettyPrint(), "value": v.prettyPrint()} for n, v in varBinds]

    src_ip, src_port = _extract_transport_src(snmpEngine, stateReference)

    key_fields = _extract_key_fields(varBinds)

    record = {
        "ts": now.isoformat(timespec="microseconds"),
        "src_ip": src_ip,
        "src_port": src_port,
        "sys_uptime": key_fields.get("sys_uptime"),
        "snmp_trap_oid": key_fields.get("snmp_trap_oid"),
        "processed_lines": processed_lines,
        "var_binds": vb_struct,
    }
    _append_jsonl(record)


def run_snmp_trap_listener():
    TrapAgentAddress = get_trap_agent_address()
    if not TrapAgentAddress:
        print("Unable to determine Trap Agent Address.")
        return

    snmpEngine = engine.SnmpEngine()
    Port = 1164

    logging.basicConfig(
        filename=TEXT_LOG_FILENAME,
        filemode="w",
        format="%(asctime)s - %(message)s",
        level=logging.INFO,
    )

    start_line = f"Agent is listening SNMP Trap on {TrapAgentAddress} , Port : {Port}"
    logging.info(start_line)
    logging.info("--------------------------------------------------------------------------")

    _append_jsonl(
        {
            "ts": datetime.datetime.now().isoformat(timespec="microseconds"),
            "event": "listener_started",
            "bind_ip": TrapAgentAddress,
            "port": Port,
        }
    )

    configure_snmp_engine(snmpEngine, TrapAgentAddress, Port)
    ntfrcv.NotificationReceiver(snmpEngine, trap_callback)

    snmpEngine.transport_dispatcher.job_started(1)
    try:
        snmpEngine.transport_dispatcher.run_dispatcher()
    except Exception as e:
        logging.error(f"Error: {e}")
        _append_jsonl(
            {
                "ts": datetime.datetime.now().isoformat(timespec="microseconds"),
                "event": "listener_error",
                "error": str(e),
            }
        )
    finally:
        try:
            snmpEngine.transport_dispatcher.close_dispatcher()
        except Exception:
            pass
        _append_jsonl(
            {
                "ts": datetime.datetime.now().isoformat(timespec="microseconds"),
                "event": "listener_stopped",
            }
        )


def dtest():
    try:
        os.remove(TEXT_LOG_FILENAME)
    except Exception:
        pass
    try:
        os.remove(JSON_LOG_FILENAME)
    except Exception:
        pass


