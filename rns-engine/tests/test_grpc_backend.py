import grpc
from concurrent import futures
from proto import device_control_pb2 as pb
from proto import device_control_pb2_grpc as pbg
from bridge.grpc_backend import GrpcCommandBackend


class _FakeService(pbg.DeviceControlServiceServicer):
    def SendCommand(self, request, context):
        return pb.CommandResponse(status=pb.CommandResponse.SUCCESS,
                                  message=f"grpc:{request.device_id}")


def _start_fake_server(port):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    pbg.add_DeviceControlServiceServicer_to_server(_FakeService(), server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    return server


def test_backend_calls_send_command():
    server = _start_fake_server(50551)
    try:
        backend = GrpcCommandBackend("127.0.0.1:50551")
        resp = backend(pb.CommandRequest(device_id="bz_attenuator_corr"))
        assert resp.status == pb.CommandResponse.SUCCESS
        assert resp.message == "grpc:bz_attenuator_corr"
    finally:
        server.stop(0)


def test_backend_returns_error_on_unreachable():
    # No server on this port -> backend must return an ERROR CommandResponse, not raise.
    backend = GrpcCommandBackend("127.0.0.1:50599", timeout=2.0)
    resp = backend(pb.CommandRequest(device_id="x"))
    assert resp.status == pb.CommandResponse.ERROR
