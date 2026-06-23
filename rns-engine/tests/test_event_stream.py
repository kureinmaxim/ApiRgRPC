"""Loopback-тест стрима событий (этап 2) поверх RNS.Channel.

Мост запускается в дочернем процессе с canned event_streamer (отдаёт 3
DeviceEvent), тест выступает клиентом: открывает Link, поднимает Channel,
шлёт SubscribeMessage и собирает пришедшие DeviceEvent.

Запускать ОТДЕЛЬНОЙ pytest-сессией (RNS.Reticulum — синглтон на процесс).
"""
import os
import subprocess
import sys
import tempfile
import threading
import time

import RNS
from bridge.bridge import APP_NAME, ASPECTS, SubscribeMessage, DeviceEventMessage
from proto import device_control_pb2 as pb

TCP_PORT = 4244

_BRIDGE_RUNNER = """
import os, sys, time
import RNS
from bridge.bridge import DeviceControlBridge
from proto import device_control_pb2 as pb

tmp = sys.argv[1]

def handler(req):
    return pb.CommandResponse(status=pb.CommandResponse.SUCCESS, message="ok")

def streamer(req):
    for i in range(3):
        ev = pb.DeviceEvent(block_type=pb.BlockType.BU, device_id="mi_th_sensor",
                            event_type=pb.EventType.LIMIT_REACHED,
                            timestamp_unix_ms=1000 + i)
        yield ev
        time.sleep(0.2)

bridge = DeviceControlBridge(configdir=tmp, storagepath=tmp, handler=handler,
                             event_streamer=streamer)
with open(os.path.join(tmp, "dest_hash"), "w") as f:
    f.write(bridge.destination.hash.hex())
while True:
    bridge.start()
    time.sleep(3)
"""

SERVER_CONFIG = f"""[reticulum]
  enable_transport = No
  share_instance = No
  panic_on_interface_error = No
[interfaces]
  [[TCP Server Interface]]
    type = TCPServerInterface
    interface_enabled = yes
    listen_ip = 127.0.0.1
    listen_port = {TCP_PORT}
"""

CLIENT_CONFIG = f"""[reticulum]
  enable_transport = No
  share_instance = No
  panic_on_interface_error = No
[interfaces]
  [[TCP Client Interface]]
    type = TCPClientInterface
    interface_enabled = yes
    target_host = 127.0.0.1
    target_port = {TCP_PORT}
"""


def _write_config(directory, body):
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "config"), "w") as f:
        f.write(body)


def test_event_stream_over_channel():
    tmp = tempfile.mkdtemp(prefix="rns_stream_")
    server_dir = os.path.join(tmp, "server")
    client_dir = os.path.join(tmp, "client")
    _write_config(server_dir, SERVER_CONFIG)
    _write_config(client_dir, CLIENT_CONFIG)
    engine_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    runner = os.path.join(server_dir, "_bridge_runner_stream.py")
    with open(runner, "w") as f:
        f.write(_BRIDGE_RUNNER)

    env = dict(os.environ)
    env["PYTHONPATH"] = engine_root + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen([sys.executable, runner, server_dir], cwd=engine_root, env=env)
    try:
        dest_hash_path = os.path.join(server_dir, "dest_hash")
        deadline = time.time() + 20
        while not os.path.isfile(dest_hash_path) and time.time() < deadline:
            assert proc.poll() is None, "bridge exited early"
            time.sleep(0.2)
        assert os.path.isfile(dest_hash_path), "bridge did not publish dest_hash"
        dest_hash = bytes.fromhex(open(dest_hash_path).read().strip())

        RNS.Reticulum(configdir=client_dir)
        time.sleep(3)
        if not RNS.Transport.has_path(dest_hash):
            RNS.Transport.request_path(dest_hash)
            d = time.time() + 25
            while not RNS.Transport.has_path(dest_hash) and time.time() < d:
                time.sleep(0.1)
        assert RNS.Transport.has_path(dest_hash), "no path to bridge"

        identity = RNS.Identity.recall(dest_hash)
        out_dest = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE,
                                   APP_NAME, *ASPECTS)
        link = RNS.Link(out_dest)
        d = time.time() + 25
        while link.status != RNS.Link.ACTIVE and time.time() < d:
            time.sleep(0.1)
        assert link.status == RNS.Link.ACTIVE, "link not active"

        channel = link.get_channel()
        channel.register_message_type(SubscribeMessage)
        channel.register_message_type(DeviceEventMessage)
        events = []
        done = threading.Event()

        def on_msg(msg):
            if isinstance(msg, DeviceEventMessage):
                ev = pb.DeviceEvent()
                ev.ParseFromString(msg.data)
                events.append(ev)
                if len(events) >= 3:
                    done.set()
                return True
            return False

        channel.add_message_handler(on_msg)

        # дождаться готовности канала и подписаться
        d = time.time() + 10
        while not channel.is_ready_to_send() and time.time() < d:
            time.sleep(0.05)
        req = pb.EventSubscribeRequest(block_type=pb.BlockType.BU)
        channel.send(SubscribeMessage(req.SerializeToString()))

        assert done.wait(timeout=20), f"got {len(events)} events, expected 3"
        assert len(events) >= 3
        assert events[0].device_id == "mi_th_sensor"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
