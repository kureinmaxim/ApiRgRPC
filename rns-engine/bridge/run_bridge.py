"""Запуск RNS-моста на VPS.

Связывает приём запроса по Reticulum (DeviceControlBridge) с локальным gRPC
DeviceControlService (GrpcCommandBackend). Транспорт (TCP сейчас, I2P позже)
задаётся конфигом RNS в --config; код моста при смене интерфейса не меняется.

Пример:
    python -m bridge.run_bridge --grpc 127.0.0.1:50051 \
        --config ./_rnscfg --storage ./_rnsdata
"""
import argparse
import time

from bridge.bridge import DeviceControlBridge
from bridge.grpc_backend import GrpcCommandBackend

# Интервал повторного announce, сек (чтобы клиенты находили путь к мосту).
ANNOUNCE_INTERVAL = 60


def main() -> None:
    parser = argparse.ArgumentParser(description="RNS bridge for DeviceControlService")
    parser.add_argument("--grpc", default="127.0.0.1:50051",
                        help="адрес локального DeviceControlService (gRPC)")
    parser.add_argument("--config", required=True, help="configdir для RNS")
    parser.add_argument("--storage", required=True,
                        help="storagepath (хранит стабильную identity моста)")
    parser.add_argument("--udp-target", default=None,
                        help="HOST:PORT UDP-прокси для пути /udp_raw (опционально)")
    args = parser.parse_args()

    udp_target = None
    if args.udp_target:
        host, _, port = args.udp_target.rpartition(":")
        udp_target = (host, int(port))

    backend = GrpcCommandBackend(args.grpc)
    bridge = DeviceControlBridge(args.config, args.storage, handler=backend,
                                 udp_target=udp_target,
                                 event_streamer=backend.subscribe_events)
    bridge.start()
    print(f"bridge up, destination = {bridge.destination.hash.hex()}", flush=True)
    print(f"grpc backend = {args.grpc}", flush=True)
    print("event stream /subscribe enabled (RNS Channel)", flush=True)
    if udp_target:
        print(f"udp path /udp_raw enabled -> {udp_target[0]}:{udp_target[1]}", flush=True)
    else:
        print("udp path /udp_raw disabled (no --udp-target)", flush=True)

    while True:
        time.sleep(ANNOUNCE_INTERVAL)
        bridge.start()  # периодический повторный announce


if __name__ == "__main__":
    main()
