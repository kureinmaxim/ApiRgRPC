"""device_control.py — клиент device-control к HA-мосту поверх RNS.

Общий код для `rns_cli.py` (терминал) и `rns_engine.py` (sidecar для Tauri).
Использует тот же контракт, что `bridge/` (APP_NAME / ASPECTS / REQUEST_PATH),
и переиспользует уже запущенный RNS-инстанс (singleton) — RNS поднимает движок.
"""
import threading
import time

import RNS

from proto import device_control_pb2 as pb
from bridge.bridge import (
    APP_NAME,
    ASPECTS,
    REQUEST_PATH,
    REQUEST_PATH_UDP,
    DeviceEventMessage,
    SubscribeMessage,
)


def block_type(name: str):
    """Имя блока ('BU'/'BZ'/'BF'/'SHSKM') → enum pb.BlockType (BU по умолч.)."""
    return getattr(pb.BlockType, (name or "BU").upper(), pb.BlockType.BU)


class DeviceControl:
    """Unary-запросы (/device_control, /udp_raw) и стрим событий (RNS.Channel)
    к HA-мосту. RNS уже должен быть запущен (движком/CLI)."""

    def __init__(self, bridge_hash_hex: str = "", timeout: float = 20.0):
        self.timeout = timeout
        self.bridge_hash = bytes.fromhex(bridge_hash_hex) if bridge_hash_hex else None

    def set_hash(self, bridge_hash_hex: str) -> None:
        self.bridge_hash = bytes.fromhex(bridge_hash_hex) if bridge_hash_hex else None

    def has_path(self) -> bool:
        return bool(self.bridge_hash) and RNS.Transport.has_path(self.bridge_hash)

    def hops(self):
        if not self.has_path():
            return None
        try:
            return RNS.Transport.hops_to(self.bridge_hash)
        except Exception:
            return None

    def _open_link(self):
        if not self.bridge_hash:
            raise ValueError("bridge hash не задан")
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
        kw = {"block_type": block_type(block), "device_id": device_id, "command_code": code}
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

    def stream(self, on_event, max_events: int = 5, block: str = "BU", timeout: float = 30.0) -> int:
        """Подписка на поток DeviceEvent. on_event(DeviceEvent) — на каждое событие."""
        link = self._open_link()
        channel = link.get_channel()
        channel.register_message_type(SubscribeMessage)
        channel.register_message_type(DeviceEventMessage)
        state, done = {"n": 0}, threading.Event()

        def on_msg(msg):
            if isinstance(msg, DeviceEventMessage):
                ev = pb.DeviceEvent()
                ev.ParseFromString(msg.data)
                on_event(ev)
                state["n"] += 1
                if max_events and state["n"] >= max_events:
                    done.set()
                return True
            return False

        channel.add_message_handler(on_msg)
        deadline = time.time() + 10
        while not channel.is_ready_to_send() and time.time() < deadline:
            time.sleep(0.05)
        req = pb.EventSubscribeRequest(block_type=block_type(block))
        channel.send(SubscribeMessage(req.SerializeToString()))
        done.wait(timeout=timeout)
        try:
            link.teardown()
        except Exception:
            pass
        return state["n"]
