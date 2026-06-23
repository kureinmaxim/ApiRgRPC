"""RNS bridge: receives CommandRequest over Reticulum, returns CommandResponse.
Transport (TCP now, I2P later) is set by the RNS config (configdir); this code is transport-agnostic."""
import os
import socket
from typing import Callable, Optional, Tuple
import RNS
from proto import device_control_pb2 as pb

APP_NAME = "apirgrpc"
ASPECTS = ("bridge", "devicecontrol")
REQUEST_PATH = "/device_control"
REQUEST_PATH_UDP = "/udp_raw"
CommandHandler = Callable[[pb.CommandRequest], pb.CommandResponse]


class DeviceControlBridge:
    def __init__(self, configdir: str, storagepath: str, handler: CommandHandler,
                 udp_target: Optional[Tuple[str, int]] = None,
                 udp_timeout: float = 5.0):
        os.makedirs(storagepath, exist_ok=True)
        self._handler = handler
        self._udp_target = udp_target
        self._udp_timeout = udp_timeout
        self.reticulum = RNS.Reticulum(configdir=configdir)
        id_path = os.path.join(storagepath, "bridge_identity")
        if os.path.isfile(id_path):
            self.identity = RNS.Identity.from_file(id_path)
        else:
            self.identity = RNS.Identity()
            self.identity.to_file(id_path)
        self.destination = RNS.Destination(self.identity, RNS.Destination.IN,
            RNS.Destination.SINGLE, APP_NAME, *ASPECTS)
        self.destination.register_request_handler(REQUEST_PATH,
            response_generator=self._on_request, allow=RNS.Destination.ALLOW_ALL)
        # Optional raw-UDP forwarding path: tunnels raw bytes over Reticulum to a
        # configured UDP proxy target and returns the single datagram reply.
        if self._udp_target is not None:
            self.destination.register_request_handler(REQUEST_PATH_UDP,
                response_generator=self._on_udp_request, allow=RNS.Destination.ALLOW_ALL)

    def start(self) -> None:
        self.destination.announce()

    def _on_request(self, path, data, request_id, link_id, remote_identity, requested_at):
        req = pb.CommandRequest()
        try:
            req.ParseFromString(data or b"")
        except Exception as exc:
            return pb.CommandResponse(status=pb.CommandResponse.ERROR,
                                      message=f"bad request: {exc}").SerializeToString()
        return self._handler(req).SerializeToString()

    def _on_udp_request(self, path, data, request_id, link_id, remote_identity, requested_at):
        """Forward raw bytes to the UDP proxy target and return the reply.

        Uses a fresh UDP socket per request, waits up to ``udp_timeout`` for one
        datagram reply, and returns its bytes. Returns b"" on timeout/error
        rather than raising, so a missing reply does not break the RNS link."""
        host, port = self._udp_target
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.settimeout(self._udp_timeout)
            sock.sendto(data or b"", (host, port))
            reply, _addr = sock.recvfrom(65535)
            return reply
        except OSError:
            return b""
        finally:
            sock.close()
