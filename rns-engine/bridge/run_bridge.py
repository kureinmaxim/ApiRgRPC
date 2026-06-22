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
    args = parser.parse_args()

    backend = GrpcCommandBackend(args.grpc)
    bridge = DeviceControlBridge(args.config, args.storage, handler=backend)
    bridge.start()
    print(f"bridge up, destination = {bridge.destination.hash.hex()}", flush=True)
    print(f"grpc backend = {args.grpc}", flush=True)

    while True:
        time.sleep(ANNOUNCE_INTERVAL)
        bridge.start()  # периодический повторный announce


if __name__ == "__main__":
    main()
