# snmpsubsystem.py
import asyncio
import asyncssh
import threading
from typing import Tuple, Optional
from MainConnectFunc import json_input

# ---------- значения по умолчанию ----------
DEFAULT_DEVICE_IP = ""
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = ""
DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = 1161
DEFAULT_TIMEOUT = 2.0


# ---------------------------------------------------------------
class SnmpSshProxy(asyncio.DatagramProtocol):
    def __init__(
            self,
            ssh_host: str,
            username: str,
            password: str,
            listen_addr: Tuple[str, int] = (DEFAULT_LISTEN_HOST, DEFAULT_LISTEN_PORT),
            response_timeout: float = DEFAULT_TIMEOUT,
    ):
        self.ssh_host = ssh_host
        self.username = username
        self.password = password
        self.listen_addr = listen_addr
        self.response_timeout = response_timeout

        self.transport: Optional[asyncio.transports.DatagramTransport] = None
        self.conn: Optional[asyncssh.SSHClientConnection] = None
        self.proc: Optional[asyncssh.SSHClientProcess] = None

        self._inflight = asyncio.Lock()
        self._closed = asyncio.Event()

    # ---------------- UDP hooks ----------------
    def connection_made(self, transport):
        self.transport = transport
        sock = transport.get_extra_info("socket")
        addr = sock.getsockname() if sock else self.listen_addr
        print(f"[proxy] UDP listening on {addr[0]}:{addr[1]} (Ctrl+C/close to stop)")

    def error_received(self, exc):
        print(f"[proxy] UDP error: {exc!r}")

    def connection_lost(self, exc):
        print(f"[proxy] UDP closed")
        self.transport = None

    def datagram_received(self, data: bytes, addr):
        asyncio.create_task(self._handle_datagram(data, addr))

    # -------------- SSH helpers ----------------
    async def _close_ssh(self):
        try:
            if self.proc:
                try:
                    self.proc.stdin.write_eof()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if self.conn:
                self.conn.close()
                await self.conn.wait_closed()
        except Exception:
            pass
        self.conn = None
        self.proc = None

    def _proc_alive(self) -> bool:
        return bool(self.proc and self.proc.stdin and not self.proc.stdin.is_closing())

    async def _ensure_ssh(self):
        if self._proc_alive():
            return
        await self._close_ssh()

        print(f"[proxy] Connecting SSH to {self.username}@{self.ssh_host} …")
        self.conn = await asyncssh.connect(
            self.ssh_host,
            username=self.username,
            password=self.password,
            known_hosts=None,
            keepalive_interval=5,
        )
        try:
            self.proc = await self.conn.create_process(subsystem="snmp", encoding=None)
        except Exception as e:
            await self._close_ssh()
            raise RuntimeError(f"Failed to open SSH subsystem 'snmp': {e}") from e

        print("[proxy] SSH 'snmp' subsystem is ready")

    # ---------------- Core ---------------------
    async def _handle_datagram(self, data: bytes, addr):
        async with self._inflight:
            try:
                await self._ensure_ssh()

                self.proc.stdin.write(data)
                await self.proc.stdin.drain()

                # чтение ответа
                reply = await self._read_reply_with_timeout(self.response_timeout)
                if reply:
                    if self.transport:
                        self.transport.sendto(reply, addr)
                else:
                    print("[proxy] No reply from SSH subsystem within timeout")

            except (asyncssh.Error, OSError, RuntimeError) as e:
                print(f"[proxy] SSH/IO error: {e}")
                await self._close_ssh()

    async def _read_reply_with_timeout(self, timeout: float) -> bytes:
        if not self.proc:
            return b""
        buf = bytearray()
        try:
            first = await asyncio.wait_for(self.proc.stdout.read(65535), timeout)
            if not first:
                return b""
            buf.extend(first)

            while True:
                try:
                    more = await asyncio.wait_for(self.proc.stdout.read(65535), 0.01)
                except asyncio.TimeoutError:
                    break
                buf.extend(more)
        except asyncio.TimeoutError:
            return b""
        return bytes(buf)

    # -------------- lifecycle ------------------
    async def start(self):
        if self.transport:
            return
        loop = asyncio.get_running_loop()

        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: self,
            local_addr=self.listen_addr
        )

        sock = self.transport.get_extra_info("socket")
        ip, port = sock.getsockname()
        await json_input(["CurrentEQ", "snmp_port"], port)
        if sock:
            self.listen_addr = sock.getsockname()

        self._closed.clear()

    async def stop(self):
        if self.transport:
            self.transport.close()
            self.transport = None
        await self._close_ssh()
        self._closed.set()


# ================= Controller (start/close) =================
class ProxyController:
    def __init__(self):
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self.proxy: Optional[SnmpSshProxy] = None
        self._lock = threading.RLock()

    def _ensure_loop(self):
        with self._lock:
            if self.loop and self.loop.is_running():
                return
            self.loop = asyncio.new_event_loop()

            def _runner():
                asyncio.set_event_loop(self.loop)
                self.loop.run_forever()

            self.thread = threading.Thread(target=_runner, daemon=True)
            self.thread.start()

    def _call_coro(self, coro):
        self._ensure_loop()
        return asyncio.run_coroutine_threadsafe(coro, self.loop)  # commands

    def start(
            self,
            ip: str = DEFAULT_DEVICE_IP,
            username: str = DEFAULT_USERNAME,
            password: str = DEFAULT_PASSWORD,
            listen_host: str = DEFAULT_LISTEN_HOST,
            listen_port: int = DEFAULT_LISTEN_PORT,
            timeout: float = DEFAULT_TIMEOUT,
    ):
        with self._lock:
            # Если прокси уже существует, закрываем его перед созданием нового
            if self.proxy is not None:
                try:
                    self.close()
                except Exception:
                    pass
                self.proxy = None


            self.proxy = SnmpSshProxy(
                ssh_host=ip,
                username=username,
                password=password,
                listen_addr=(listen_host, listen_port),
                response_timeout=timeout,
            )

        print(f"SNMP proxy will listen on {listen_host}:{listen_port} (UDP). Type 'close' to stop.")

        fut = self._call_coro(self.proxy.start())
        try:
            fut.result()
            real_host, real_port = self.proxy.listen_addr
            print(f"[proxy] STARTED: Listening on {real_host}:{real_port} (UDP)")
        except Exception as e:
            print(f"[proxy] start failed: {e}")

    def close(self):
        with self._lock:
            if not self.proxy:
                print("[proxy] nothing to stop")
                return

            fut = self._call_coro(self.proxy.stop())
            try:
                fut.result()
            except Exception as e:
                print(f"[proxy] stop failed: {e}")
            finally:
                self.proxy = None

    def dispose(self):
        try:
            if self.proxy:
                self.close()
        finally:
            with self._lock:
                if self.loop and self.loop.is_running():
                    self.loop.call_soon_threadsafe(self.loop.stop)
                    if self.thread:
                        self.thread.join(timeout=1.0)
                self.loop = None
                self.thread = None
                self.proxy = None


# ======================= консоль =======================
def repl():
    ctrl = ProxyController()
    print("Type: start [ip] [user] [pass] [host] [port] | close | exit")
    try:
        while True:
            line = input("> ").strip()
            if not line:
                continue
            parts = line.split()
            cmd = parts[0].lower()

            if cmd == "start":
                ip = parts[1] if len(parts) > 1 else DEFAULT_DEVICE_IP
                user = parts[2] if len(parts) > 2 else DEFAULT_USERNAME
                pwd = parts[3] if len(parts) > 3 else DEFAULT_PASSWORD
                host = parts[4] if len(parts) > 4 else DEFAULT_LISTEN_HOST
                port = int(parts[5]) if len(parts) > 5 else DEFAULT_LISTEN_PORT
                ctrl.start(ip=ip, username=user, password=pwd, listen_host=host, listen_port=port)

            elif cmd == "close":
                ctrl.close()

            elif cmd in ("exit", "quit"):
                break

            else:
                print("Unknown command. Use: start | close | exit")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        ctrl.dispose()
        print("Bye.")


if __name__ == "__main__":
    repl()
