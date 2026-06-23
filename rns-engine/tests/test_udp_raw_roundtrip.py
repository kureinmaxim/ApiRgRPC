"""Loopback round-trip test for the RNS bridge's /udp_raw path.

Like ``test_rns_roundtrip.py`` this needs two separate RNS instances, so the
bridge runs in a child process (TCPServerInterface on its own TCP port) and the
test acts as the client (TCPClientInterface). In addition, the TEST process runs
a tiny UDP echo server on 127.0.0.1:54545; the bridge is configured with that as
its ``udp_target``. A raw-bytes request over /udp_raw must be forwarded to the
UDP echo server and the reply (``b"udp-echo:" + data``) returned as the RNS
response.
"""
import os, sys, time, tempfile, threading, socket, subprocess, textwrap
import RNS
from bridge.bridge import APP_NAME, ASPECTS, REQUEST_PATH_UDP

UDP_ECHO_HOST = "127.0.0.1"
UDP_ECHO_PORT = 54545  # outside the 50508-50607 range
TCP_PORT = 50061

# --- bridge child process ---------------------------------------------------
# Runs the real DeviceControlBridge with a stub proto handler AND a udp_target,
# writes its destination hash to <storagepath>/dest_hash, then keeps announcing.
_BRIDGE_RUNNER = textwrap.dedent(
    """
    import os, sys, time
    import RNS
    from bridge.bridge import DeviceControlBridge
    from proto import device_control_pb2 as pb

    tmp = sys.argv[1]
    udp_host = sys.argv[2]
    udp_port = int(sys.argv[3])

    def handler(req):
        return pb.CommandResponse(status=pb.CommandResponse.SUCCESS,
                                  message=f"echo:{req.device_id}")

    bridge = DeviceControlBridge(configdir=tmp, storagepath=tmp, handler=handler,
                                 udp_target=(udp_host, udp_port))
    with open(os.path.join(tmp, "dest_hash"), "w") as f:
        f.write(RNS.hexrep(bridge.destination.hash, delimit=False))
    while True:
        bridge.start()  # announce
        time.sleep(3)
    """
)

SERVER_CONFIG = f"""
[reticulum]
  enable_transport = Yes
  share_instance = No
[interfaces]
  [[TCPServer]]
    type = TCPServerInterface
    interface_enabled = yes
    listen_ip = 127.0.0.1
    listen_port = {TCP_PORT}
"""

CLIENT_CONFIG = f"""
[reticulum]
  enable_transport = No
  share_instance = No
[interfaces]
  [[TCPClientLoopback]]
    type = TCPClientInterface
    interface_enabled = yes
    target_host = 127.0.0.1
    target_port = {TCP_PORT}
"""


def _write_config(tmp, body):
    os.makedirs(tmp, exist_ok=True)
    with open(os.path.join(tmp, "config"), "w") as f:
        f.write(body)
    return tmp


def _start_udp_echo(host, port, stop):
    """UDP echo server: replies b"udp-echo:" + data to each datagram."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.settimeout(0.5)

    def loop():
        while not stop.is_set():
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            sock.sendto(b"udp-echo:" + data, addr)
        sock.close()

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


def test_udp_raw_roundtrip_over_tcp():
    stop = threading.Event()
    _start_udp_echo(UDP_ECHO_HOST, UDP_ECHO_PORT, stop)

    server_dir = _write_config(tempfile.mkdtemp(), SERVER_CONFIG)
    client_dir = _write_config(tempfile.mkdtemp(), CLIENT_CONFIG)

    engine_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    runner_path = os.path.join(server_dir, "_bridge_runner_udp.py")
    with open(runner_path, "w") as f:
        f.write(_BRIDGE_RUNNER)

    env = dict(os.environ)
    env["PYTHONPATH"] = engine_root + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.Popen(
        [sys.executable, runner_path, server_dir, UDP_ECHO_HOST, str(UDP_ECHO_PORT)],
        cwd=engine_root, env=env)
    try:
        dest_hash_path = os.path.join(server_dir, "dest_hash")
        deadline = time.time() + 20
        while not os.path.isfile(dest_hash_path) and time.time() < deadline:
            assert proc.poll() is None, "bridge process exited early"
            time.sleep(0.2)
        assert os.path.isfile(dest_hash_path), "bridge never published dest_hash"
        with open(dest_hash_path) as f:
            dest_hash = bytes.fromhex(f.read().strip())

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
            result["resp"] = receipt.response
            done.set()

        link.request(REQUEST_PATH_UDP, data=b"hello",
                     response_callback=on_response,
                     failed_callback=lambda r: done.set())
        assert done.wait(timeout=20), "no response within timeout"
        assert result.get("resp") == b"udp-echo:hello", result.get("resp")
    finally:
        stop.set()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
