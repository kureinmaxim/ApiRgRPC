"""RNS bridge: receives CommandRequest over Reticulum, returns CommandResponse.
Transport (TCP now, I2P later) is set by the RNS config (configdir); this code is transport-agnostic."""
import os
from typing import Callable
import RNS
from proto import device_control_pb2 as pb

APP_NAME = "apirgrpc"
ASPECTS = ("bridge", "devicecontrol")
REQUEST_PATH = "/device_control"
CommandHandler = Callable[[pb.CommandRequest], pb.CommandResponse]


class DeviceControlBridge:
    def __init__(self, configdir: str, storagepath: str, handler: CommandHandler):
        os.makedirs(storagepath, exist_ok=True)
        self._handler = handler
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
