from proto import device_control_pb2 as pb


def test_command_request_roundtrip():
    req = pb.CommandRequest(device_id="bu_led_status")
    data = req.SerializeToString()
    back = pb.CommandRequest()
    back.ParseFromString(data)
    assert back.device_id == "bu_led_status"


def test_command_response_status_enum():
    resp = pb.CommandResponse(status=pb.CommandResponse.SUCCESS, message="ok")
    assert resp.status == pb.CommandResponse.SUCCESS
    assert resp.message == "ok"
