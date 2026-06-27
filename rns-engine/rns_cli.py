#!/usr/bin/env python3
"""rns_cli.py — терминальный CLI для ApiRgRPC поверх движка rns_engine.

Два режима в одном REPL (общий RNS-инстанс, singleton):
  • Мессенджер (LXMF): address / announce / status / name / peers / send +
    живой приём входящих сообщений и анонсов пиров.
  • Device-control к HA-мосту (по RNS, тот же контракт, что у bridge/):
    dev ping / read / write / raw / stream / hash / status.

Это «человеческая» обёртка над движком (который сам по себе общается с Tauri
сырым JSON через stdin/stdout). Запуск:

    cd rns-engine
    python -m pip install -r requirements.txt
    python rns_cli.py --store ./store --name Alice [--config <rns_cfg_dir>] \
                      [--bridge-hash <hex>]

Подсказки в REPL — команда `help`. Выход — `quit` / `exit` / Ctrl-D.
"""
import argparse
import os
import shlex
import sys
import threading
import time

# Каталог движка в sys.path, чтобы импортировались top-level пакеты proto/ и bridge/.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import rns_engine  # noqa: E402  (переопределяем его emit ниже)

try:
    import RNS  # noqa: E402
    from proto import device_control_pb2 as pb  # noqa: E402
    from bridge.bridge import (  # noqa: E402
        APP_NAME,
        ASPECTS,
        REQUEST_PATH,
        REQUEST_PATH_UDP,
        DeviceEventMessage,
        SubscribeMessage,
    )
except Exception as exc:  # pragma: no cover - import guard
    sys.stderr.write(f"rns_cli: не удалось импортировать зависимости: {exc}\n"
                     f"Поставь их: pip install -r requirements.txt\n")
    sys.exit(1)


# --------------------------------------------------------------------------- #
#  Человеческий вывод событий движка (вместо JSON-emit для Tauri)
# --------------------------------------------------------------------------- #
_print_lock = threading.Lock()


def _p(text: str = "") -> None:
    with _print_lock:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()


def _cli_emit(obj: dict) -> None:
    ev = obj.get("event")
    if ev == "rx":
        who = obj.get("name") or (obj.get("from", "")[:16] + "…")
        title = obj.get("title", "")
        _p(f"\n📨 [{who}] {title + ': ' if title else ''}{obj.get('text', '')}")
    elif ev == "announce":
        _p(f"📡 пир: {obj.get('name') or '(без имени)'}  {obj.get('hash', '')[:16]}…")
    elif ev == "sent":
        _p(f"   → {obj.get('peer', '')[:16]}…: {obj.get('state')}")
    elif ev == "ready":
        _p(f"✅ движок готов — адрес {obj.get('address')}  имя {obj.get('name')}")
    elif ev == "address":
        _p(f"🔑 {obj.get('address')}")
    elif ev == "status":
        _p(f"🛰 addr {obj.get('address')}  имя {obj.get('name')}  "
           f"transport={obj.get('transport')}  интерфейсов={len(obj.get('interfaces', []))}  "
           f"пиров={obj.get('peers')}")
        for i in obj.get("interfaces", []):
            _p(f"     • {i}")
    elif ev == "log":
        _p(f"   [{obj.get('level')}] {obj.get('message')}")
    elif ev == "error":
        _p(f"❌ {obj.get('message')}")
    else:  # неизвестное событие — как есть
        _p(str(obj))


# Движок и его log() используют module-level emit — перенаправляем на CLI-вывод.
rns_engine.emit = _cli_emit


# --------------------------------------------------------------------------- #
#  Device-control клиент к HA-мосту (переиспользует запущенный RNS singleton)
# --------------------------------------------------------------------------- #
def _block(name: str):
    return getattr(pb.BlockType, (name or "BU").upper(), pb.BlockType.BU)


class DeviceControl:
    def __init__(self, bridge_hash_hex: str = "", timeout: float = 20.0):
        self.timeout = timeout
        self.bridge_hash = bytes.fromhex(bridge_hash_hex) if bridge_hash_hex else None

    def _open_link(self):
        if not self.bridge_hash:
            raise ValueError("bridge hash не задан — `dev hash <hex>` или --bridge-hash")
        h = self.bridge_hash
        if not RNS.Transport.has_path(h):
            RNS.Transport.request_path(h)
            deadline = time.time() + self.timeout
            while not RNS.Transport.has_path(h) and time.time() < deadline:
                time.sleep(0.1)
        if not RNS.Transport.has_path(h):
            raise TimeoutError("нет пути к мосту (transport прогревается / мост недоступен?)")
        identity = RNS.Identity.recall(h)
        if identity is None:
            raise TimeoutError("не удалось получить identity моста")
        dest = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, *ASPECTS)
        link = RNS.Link(dest)
        deadline = time.time() + self.timeout
        while link.status != RNS.Link.ACTIVE and time.time() < deadline:
            time.sleep(0.1)
        if link.status != RNS.Link.ACTIVE:
            raise TimeoutError("link не активировался")
        return link

    def _request(self, path: str, data: bytes) -> bytes:
        link = self._open_link()
        result, done = {}, threading.Event()
        link.request(
            path, data=data,
            response_callback=lambda r: (result.__setitem__("resp", r.response), done.set()),
            failed_callback=lambda r: done.set(),
        )
        ok = done.wait(timeout=self.timeout)
        try:
            link.teardown()
        except Exception:
            pass
        if not ok or "resp" not in result:
            raise TimeoutError("нет ответа от моста")
        return result["resp"]

    def command(self, device_id: str, code, *, led=None, payload=None, block="BU"):
        kw = {"block_type": _block(block), "device_id": device_id, "command_code": code}
        if led is not None:
            kw["set_led_state"] = pb.SetLedStatePayload(state=led)
        elif payload is not None:
            kw["generic_payload"] = payload
        req = pb.CommandRequest(**kw)
        resp = pb.CommandResponse()
        resp.ParseFromString(self._request(REQUEST_PATH, req.SerializeToString()))
        return resp

    def raw(self, data: bytes) -> bytes:
        return self._request(REQUEST_PATH_UDP, data)

    def stream(self, max_events: int = 5, block: str = "BU", timeout: float = 30.0) -> int:
        link = self._open_link()
        channel = link.get_channel()
        channel.register_message_type(SubscribeMessage)
        channel.register_message_type(DeviceEventMessage)
        state, done = {"n": 0}, threading.Event()

        def on_msg(msg):
            if isinstance(msg, DeviceEventMessage):
                ev = pb.DeviceEvent()
                ev.ParseFromString(msg.data)
                payload = ev.payload.decode("utf-8", "replace") if ev.payload else ""
                _p(f"event: {ev.device_id} type={pb.EventType.Name(ev.event_type)} "
                   f"ts={ev.timestamp_unix_ms} payload='{payload}'")
                state["n"] += 1
                if max_events and state["n"] >= max_events:
                    done.set()
                return True
            return False

        channel.add_message_handler(on_msg)
        deadline = time.time() + 10
        while not channel.is_ready_to_send() and time.time() < deadline:
            time.sleep(0.05)
        req = pb.EventSubscribeRequest(block_type=_block(block))
        channel.send(SubscribeMessage(req.SerializeToString()))
        done.wait(timeout=timeout)
        try:
            link.teardown()
        except Exception:
            pass
        return state["n"]


# --------------------------------------------------------------------------- #
#  REPL
# --------------------------------------------------------------------------- #
HELP = """Команды:
  Мессенджер (LXMF):
    address                 — показать свой RNS-адрес
    announce                — анонсировать себя в сети
    status                  — статус: адрес/имя/transport/интерфейсы/пиры
    name <новое имя>        — сменить отображаемое имя (+ре-анонс)
    peers                   — известные пиры (по их announce)
    send <peer_hex> <текст> — отправить LXMF-сообщение
  Device-control (HA-мост по RNS):
    dev hash [<hex>]        — показать/задать destination hash моста
    dev status              — есть ли путь к мосту
    dev ping                — round-trip (READ mi_th_sensor) + latency
    dev read <device>       — proto READ устройства
    dev write <device> on|off — proto WRITE (лампочка)
    dev raw <HEX...>        — сырой /udp_raw (напр. dev raw 01 00)
    dev stream [N]          — подписка на поток DeviceEvent (N событий, по умолч. 5)
  Прочее:
    help                    — эта справка
    quit / exit / Ctrl-D    — выход

Входящие сообщения и анонсы пиров печатаются автоматически (📨 / 📡)."""


def _handle_dev(dc: DeviceControl, args: list) -> None:
    if not args:
        _p("dev: hash | status | ping | read | write | raw | stream  (см. help)")
        return
    sub = args[0].lower()
    if sub == "hash":
        if len(args) < 2:
            _p(f"bridge hash: {dc.bridge_hash.hex() if dc.bridge_hash else '(не задан)'}")
            return
        dc.bridge_hash = bytes.fromhex(args[1])
        _p(f"bridge hash = {args[1]}")
    elif sub == "status":
        if not dc.bridge_hash:
            _p("bridge hash не задан (dev hash <hex>)")
            return
        has = RNS.Transport.has_path(dc.bridge_hash)
        line = "да" if has else "нет"
        if has:
            try:
                line += f" (hops={RNS.Transport.hops_to(dc.bridge_hash)})"
            except Exception:
                pass
        _p(f"мост {dc.bridge_hash.hex()}  путь известен: {line}")
    elif sub == "ping":
        t0 = time.time()
        resp = dc.command("mi_th_sensor", pb.CommandCode.READ)
        dt = (time.time() - t0) * 1000.0
        ok = resp.status == pb.CommandResponse.Status.SUCCESS
        _p((f"✅ HA round-trip ok ({dt:.0f} ms): {resp.message}") if ok
           else f"❌ HA error ({dt:.0f} ms): {resp.message}")
    elif sub == "read":
        if len(args) < 2:
            _p("dev read <device>")
            return
        resp = dc.command(args[1], pb.CommandCode.READ)
        _p(resp.message)
        if resp.read_data:
            _p(f"read_data: {resp.read_data.hex(' ')}")
    elif sub == "write":
        if len(args) < 3 or args[2].lower() not in ("on", "off"):
            _p("dev write <device> on|off")
            return
        resp = dc.command(args[1], pb.CommandCode.WRITE, led=(args[2].lower() == "on"))
        _p(resp.message)
    elif sub == "raw":
        if len(args) < 2:
            _p("dev raw <HEX...>  напр. dev raw 01 00")
            return
        try:
            data = bytes.fromhex("".join(args[1:]))
        except ValueError:
            _p("dev raw: некорректный HEX")
            return
        resp = dc.raw(data)
        _p(f"raw resp ({len(resp)} b): {resp.hex(' ')}")
    elif sub == "stream":
        n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 5
        _p(f"подписка на DeviceEvent (max={n})…")
        got = dc.stream(max_events=n)
        _p(f"received {got} events")
    else:
        _p(f"dev: неизвестная подкоманда '{sub}' (см. help)")


def main() -> None:
    parser = argparse.ArgumentParser(description="ApiRgRPC Reticulum CLI (мессенджер + device-control)")
    parser.add_argument("--config", default=None, help="каталог конфига Reticulum (~/.reticulum по умолч.)")
    parser.add_argument("--store", default="./store", help="каталог хранилища движка (identity, LXMF)")
    parser.add_argument("--name", default="ApiRgRPC", help="отображаемое имя")
    parser.add_argument("--bridge-hash", default=None,
                        help="destination hash HA-моста (hex). Иначе из $RETICULUM_BRIDGE_HASH.")
    args = parser.parse_args()

    try:
        engine = rns_engine.Engine(args.config, args.store, args.name)
    except Exception as exc:
        _p(f"❌ не удалось поднять движок: {exc}")
        sys.exit(1)

    engine.cmd_announce()
    _cli_emit({"event": "ready", "address": engine.address_hex, "name": engine.display_name})
    _p("ApiRgRPC Reticulum CLI — наберите `help`. Выход: quit / Ctrl-D.")

    dc = DeviceControl((args.bridge_hash or os.environ.get("RETICULUM_BRIDGE_HASH", "")).strip())

    while True:
        try:
            line = input("rns> ").strip()
        except (EOFError, KeyboardInterrupt):
            _p("")
            break
        if not line:
            continue
        try:
            parts = shlex.split(line)
        except ValueError:
            parts = line.split()
        cmd = parts[0].lower()
        try:
            if cmd in ("quit", "exit"):
                break
            elif cmd == "help":
                _p(HELP)
            elif cmd == "address":
                engine.cmd_address()
            elif cmd == "announce":
                engine.cmd_announce()
            elif cmd == "status":
                engine.cmd_status()
            elif cmd == "name":
                if len(parts) < 2:
                    _p("name <новое имя>")
                else:
                    engine.cmd_set_name(" ".join(parts[1:]))
            elif cmd == "peers":
                if not engine.peers:
                    _p("(пиров пока нет — дождись announce'ов или сделай announce сам)")
                for h, n in engine.peers.items():
                    _p(f"  {h[:16]}…  {n or '(без имени)'}")
            elif cmd == "send":
                if len(parts) < 3:
                    _p("send <peer_hex> <текст...>")
                else:
                    engine.cmd_send(parts[1], " ".join(parts[2:]))
            elif cmd == "dev":
                _handle_dev(dc, parts[1:])
            else:
                _p(f"неизвестная команда: {cmd}  (наберите help)")
        except Exception as exc:
            _p(f"❌ {exc}")

    _p("bye")


if __name__ == "__main__":
    main()
