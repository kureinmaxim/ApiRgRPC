"""Loopback round-trip test for the RNS DeviceControlBridge.

RNS.Reticulum is a process-wide singleton and refuses to establish a Link to a
destination owned by the *same* instance (a self-loop never activates). A
genuine request/response round-trip therefore requires two separate RNS
instances. Since two instances cannot coexist in one process, the bridge runs in
a child process (TCPServerInterface) and the test acts as the client
(TCPClientInterface) connecting back to it over 127.0.0.1:4242. Both sides use
the real ``DeviceControlBridge`` and the exact wire conventions
(APP_NAME / ASPECTS / REQUEST_PATH).
"""
import os, sys, time, tempfile, threading, subprocess, textwrap
import RNS
from proto import device_control_pb2 as pb
from bridge.bridge import APP_NAME, ASPECTS, REQUEST_PATH

# --- bridge child process ---------------------------------------------------
# Runs the real DeviceControlBridge with a stub echo handler, writes its
# destination hash to <storagepath>/dest_hash, then keeps announcing.
_BRIDGE_RUNNER = textwrap.dedent(
    """
    import os, sys, time
    import RNS
    from bridge.bridge import DeviceControlBridge
    from proto import device_control_pb2 as pb

    tmp = sys.argv[1]

    def handler(req):
        return pb.CommandResponse(status=pb.CommandResponse.SUCCESS,
                                  message=f"echo:{req.device_id}")

    bridge = DeviceControlBridge(configdir=tmp, storagepath=tmp, handler=handler)
    with open(os.path.join(tmp, "dest_hash"), "w") as f:
        f.write(RNS.hexrep(bridge.destination.hash, delimit=False))
    while True:
        bridge.start()  # announce
        time.sleep(3)
    """
)

SERVER_CONFIG = """
[reticulum]
  enable_transport = Yes
  share_instance = No
[interfaces]
  [[TCPServer]]
    type = TCPServerInterface
    interface_enabled = yes
    listen_ip = 127.0.0.1
    listen_port = 4242
"""

CLIENT_CONFIG = """
[reticulum]
  enable_transport = No
  share_instance = No
[interfaces]
  [[TCPClientLoopback]]
    type = TCPClientInterface
    interface_enabled = yes
    target_host = 127.0.0.1
    target_port = 4242
"""


def _write_config(tmp, body):
    os.makedirs(tmp, exist_ok=True)
    with open(os.path.join(tmp, "config"), "w") as f:
        f.write(body)
    return tmp


def test_command_roundtrip_over_tcp():
    server_dir = _write_config(tempfile.mkdtemp(), SERVER_CONFIG)
    client_dir = _write_config(tempfile.mkdtemp(), CLIENT_CONFIG)

    # rns-engine/ must be importable in the child for `bridge` and `proto`.
    engine_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    runner_path = os.path.join(server_dir, "_bridge_runner.py")
    with open(runner_path, "w") as f:
        f.write(_BRIDGE_RUNNER)

    env = dict(os.environ)
    env["PYTHONPATH"] = engine_root + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.Popen([sys.executable, runner_path, server_dir],
                            cwd=engine_root, env=env)
    try:
        # Wait for the bridge to publish its destination hash.
        dest_hash_path = os.path.join(server_dir, "dest_hash")
        deadline = time.time() + 20
        while not os.path.isfile(dest_hash_path) and time.time() < deadline:
            assert proc.poll() is None, "bridge process exited early"
            time.sleep(0.2)
        assert os.path.isfile(dest_hash_path), "bridge never published dest_hash"
        with open(dest_hash_path) as f:
            dest_hash = bytes.fromhex(f.read().strip())

        # Client side: start Reticulum, resolve the path, open a Link, request.
        RNS.Reticulum(configdir=client_dir)
        time.sleep(3)

        if not RNS.Transport.has_path(dest_hash):
            RNS.Transport.request_path(dest_hash)
            deadline = time.time() + 25
            while not RNS.Transport.has_path(dest_hash) and time.time() < deadline:
                time.sleep(0.1)
        assert RNS.Transport.has_path(dest_hash), "no path to bridge destination"

        server_identity = RNS.Identity.recall(dest_hash)
        assert server_identity is not None, "could not recall bridge identity"
        out_dest = RNS.Destination(server_identity, RNS.Destination.OUT,
                                   RNS.Destination.SINGLE, APP_NAME, *ASPECTS)
        link = RNS.Link(out_dest)
        deadline = time.time() + 25
        while link.status != RNS.Link.ACTIVE and time.time() < deadline:
            time.sleep(0.1)
        assert link.status == RNS.Link.ACTIVE, "link did not activate"

        result = {}
        done = threading.Event()

        def on_response(receipt):
            resp = pb.CommandResponse()
            resp.ParseFromString(receipt.response)
            result["resp"] = resp
            done.set()

        req = pb.CommandRequest(device_id="bu_led_status")
        link.request(REQUEST_PATH, data=req.SerializeToString(),
                     response_callback=on_response,
                     failed_callback=lambda r: done.set())
        assert done.wait(timeout=20), "no response within timeout"
        assert result.get("resp") is not None
        assert result["resp"].message == "echo:bu_led_status"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
