#!/usr/bin/env python3
"""
rns_engine.py — Reticulum (RNS + LXMF) sidecar for ApiRgRPC.

Design mirrors how ApiNgRPC drives `sing-box`: the Tauri (Rust) side spawns this
process and talks to it over a tiny line-delimited JSON protocol.

Protocol
--------
Commands  (received on STDIN, one JSON object per line):
    {"cmd": "status"}
    {"cmd": "address"}
    {"cmd": "announce"}
    {"cmd": "set_name", "name": "Alice"}
    {"cmd": "send", "peer": "<hex hash>", "text": "hello", "title": ""}
    {"cmd": "ping", "peer": "<hex hash>"}
    {"cmd": "shutdown"}

Events    (emitted on STDOUT, one JSON object per line):
    {"event": "ready",    "address": "<hex>", "name": "..."}
    {"event": "status",   "address": "<hex>", "transport": false, "interfaces": [...], "peers": N}
    {"event": "address",  "address": "<hex>"}
    {"event": "rx",       "from": "<hex>", "name": "...", "title": "...", "text": "...", "ts": 169...}
    {"event": "announce", "hash": "<hex>", "name": "..."}        # an LXMF peer appeared
    {"event": "sent",     "peer": "<hex>", "state": "delivered|failed|outbound"}
    {"event": "log",      "level": "info|warn|error", "message": "..."}
    {"event": "error",    "message": "..."}

Run standalone for testing:
    pip install rns lxmf
    python rns_engine.py --config ./.reticulum --store ./store
"""

import sys
import os
import json
import time
import argparse
import threading

try:
    import RNS
    import LXMF
except Exception as exc:  # pragma: no cover - import guard
    sys.stdout.write(json.dumps({
        "event": "error",
        "message": f"Reticulum/LXMF not installed: {exc}. Run: pip install rns lxmf",
    }) + "\n")
    sys.stdout.flush()
    sys.exit(1)


APP_NAME = "apirgrpc"
_out_lock = threading.Lock()


def emit(obj: dict) -> None:
    """Thread-safe single-line JSON event to stdout."""
    with _out_lock:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def log(message: str, level: str = "info") -> None:
    emit({"event": "log", "level": level, "message": message})


class Engine:
    def __init__(self, configdir: str, storagepath: str, display_name: str):
        os.makedirs(storagepath, exist_ok=True)
        self.storagepath = storagepath
        self.display_name = display_name
        self.peers: dict[str, str] = {}  # hash hex -> display name

        # Reticulum reads ~/.reticulum/config unless configdir is given.
        self.reticulum = RNS.Reticulum(configdir=configdir)

        # Stable identity (so our address survives restarts).
        id_path = os.path.join(storagepath, "identity")
        if os.path.isfile(id_path):
            self.identity = RNS.Identity.from_file(id_path)
        else:
            self.identity = RNS.Identity()
            self.identity.to_file(id_path)

        # LXMF router = the "mail"/messaging layer over RNS.
        self.router = LXMF.LXMRouter(
            identity=self.identity, storagepath=storagepath
        )
        self.local = self.router.register_delivery_identity(
            self.identity, display_name=self.display_name
        )
        self.router.register_delivery_callback(self._on_message)

        # Hear other LXMF nodes announcing themselves.
        RNS.Transport.register_announce_handler(_AnnounceHandler(self))

        self.address_hex = self.local.hash.hex()

    # ---- inbound -----------------------------------------------------------
    def _on_message(self, message) -> None:
        try:
            src = message.source_hash.hex() if message.source_hash else ""
            title = (message.title or b"").decode("utf-8", "replace")
            content = (message.content or b"").decode("utf-8", "replace")
            name = self.peers.get(src, "")
            emit({
                "event": "rx", "from": src, "name": name,
                "title": title, "text": content, "ts": int(time.time()),
            })
        except Exception as exc:  # pragma: no cover
            emit({"event": "error", "message": f"rx parse failed: {exc}"})

    def note_peer(self, dest_hash: bytes, name: str) -> None:
        self.peers[dest_hash.hex()] = name
        emit({"event": "announce", "hash": dest_hash.hex(), "name": name})

    # ---- commands ----------------------------------------------------------
    def cmd_address(self) -> None:
        emit({"event": "address", "address": self.address_hex})

    def cmd_announce(self) -> None:
        self.router.announce(self.local.hash)
        log("announced delivery destination")

    def cmd_set_name(self, name: str) -> None:
        self.display_name = name or self.display_name
        # Re-register with the new display name, then re-announce.
        self.local = self.router.register_delivery_identity(
            self.identity, display_name=self.display_name
        )
        self.router.announce(self.local.hash)
        log(f"display name set to {self.display_name}")

    def cmd_status(self) -> None:
        ifaces = []
        try:
            for iface in RNS.Transport.interfaces:
                ifaces.append(str(iface))
        except Exception:
            pass
        emit({
            "event": "status",
            "address": self.address_hex,
            "name": self.display_name,
            "transport": bool(getattr(self.reticulum, "transport_enabled", lambda: False)()
                              if callable(getattr(self.reticulum, "transport_enabled", None))
                              else False),
            "interfaces": ifaces,
            "peers": len(self.peers),
        })

    def cmd_send(self, peer_hex: str, text: str, title: str = "") -> None:
        try:
            dest_hash = bytes.fromhex(peer_hex)
        except ValueError:
            emit({"event": "error", "message": f"bad peer hash: {peer_hex}"})
            return

        if not RNS.Transport.has_path(dest_hash):
            RNS.Transport.request_path(dest_hash)
            # Wait briefly for the path/identity to resolve.
            deadline = time.time() + 8
            while not RNS.Transport.has_path(dest_hash) and time.time() < deadline:
                time.sleep(0.1)

        recipient_identity = RNS.Identity.recall(dest_hash)
        if recipient_identity is None:
            emit({"event": "error", "message": f"no path/identity for {peer_hex}"})
            return

        recipient = RNS.Destination(
            recipient_identity, RNS.Destination.OUT,
            RNS.Destination.SINGLE, "lxmf", "delivery",
        )
        lxm = LXMF.LXMessage(
            recipient, self.local,
            text.encode("utf-8"), title.encode("utf-8"),
            desired_method=LXMF.LXMessage.DIRECT,
        )
        lxm.register_delivery_callback(
            lambda m: emit({"event": "sent", "peer": peer_hex, "state": "delivered"})
        )
        lxm.register_failed_callback(
            lambda m: emit({"event": "sent", "peer": peer_hex, "state": "failed"})
        )
        self.router.handle_outbound(lxm)
        emit({"event": "sent", "peer": peer_hex, "state": "outbound"})


class _AnnounceHandler:
    """Surfaces other LXMF delivery destinations as they announce."""
    aspect_filter = "lxmf.delivery"

    def __init__(self, engine: "Engine"):
        self.engine = engine

    def received_announce(self, destination_hash, announced_identity, app_data):
        name = ""
        try:
            if app_data:
                # LXMF packs the display name in app_data.
                name = LXMF.display_name_from_app_data(app_data) or ""
        except Exception:
            try:
                name = app_data.decode("utf-8", "replace") if app_data else ""
            except Exception:
                name = ""
        self.engine.note_peer(destination_hash, name)


def main() -> None:
    parser = argparse.ArgumentParser(description="ApiRgRPC Reticulum engine")
    parser.add_argument("--config", default=None, help="Reticulum config dir")
    parser.add_argument("--store", default="./store", help="engine storage dir")
    parser.add_argument("--name", default="ApiRgRPC", help="display name")
    args = parser.parse_args()

    try:
        engine = Engine(args.config, args.store, args.name)
    except Exception as exc:
        emit({"event": "error", "message": f"engine init failed: {exc}"})
        sys.exit(1)

    engine.cmd_announce()
    emit({"event": "ready", "address": engine.address_hex, "name": engine.display_name})

    # Command loop: one JSON object per stdin line.
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            emit({"event": "error", "message": f"bad json: {line[:120]}"})
            continue

        cmd = msg.get("cmd")
        try:
            if cmd == "address":
                engine.cmd_address()
            elif cmd == "announce":
                engine.cmd_announce()
            elif cmd == "status":
                engine.cmd_status()
            elif cmd == "set_name":
                engine.cmd_set_name(msg.get("name", ""))
            elif cmd == "send":
                engine.cmd_send(msg.get("peer", ""), msg.get("text", ""), msg.get("title", ""))
            elif cmd == "shutdown":
                log("shutting down")
                break
            else:
                emit({"event": "error", "message": f"unknown cmd: {cmd}"})
        except Exception as exc:  # pragma: no cover
            emit({"event": "error", "message": f"cmd '{cmd}' failed: {exc}"})


if __name__ == "__main__":
    main()
