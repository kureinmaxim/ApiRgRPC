# Reticulum-транспорт — Этап 1 (PoC round-trip) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Доставить одно сообщение `device_control.proto` (`CommandRequest`→`CommandResponse`) от клиента к HA-серверу поверх Reticulum по простому `TCPInterface` и получить ответ — не трогая существующий gRPC/TCP-путь и серверы BU/BZ/BF.

**Architecture:** Новый RNS-мост в ApiRgRPC (`rns-engine/bridge/`) поднимает `RNS.Destination` с обработчиком запроса `/device_control`, декодирует прото и вызывает локальный gRPC `DeviceControlService.SendCommand` UDP_gRPC_COM_Lite, возвращая прото-ответ через `RNS.Link.request`. Клиент-отправитель — модуль `ReticulumTransport` в CLI UDP_gRPC_COM_Lite, выбираемый переключателем протокола. Транспорт Reticulum на этом этапе — `TCPInterface` (позже меняется на I2P без правок кода).

**Tech Stack:** Python 3, `rns` (Reticulum), `grpcio`/`grpcio-tools` + сгенерированные стабы из `device_control.proto`, `pytest`.

**Спецификация:** [../../RETICULUM_TRANSPORT.md](../../RETICULUM_TRANSPORT.md) (раздел 7 — чек-лист этапов; обновлять статус по ходу).

**Соглашения «по проводу» (общие для моста и клиента):**
- Destination: `app_name="apirgrpc"`, aspects `("bridge", "devicecontrol")` → тип `IN/SINGLE` на мосту, `OUT/SINGLE` на клиенте.
- Путь запроса: `"/device_control"`.
- Тело запроса = сериализованный `CommandRequest`; тело ответа = сериализованный `CommandResponse`.

> ⚠️ Перед началом сверить точную сигнатуру request-API установленной версии
> `rns` (`Destination.register_request_handler`, `Link.request`,
> `request_receipt.response`) — API стабилен, но версии 0.7.x/0.9.x могли менять
> детали. См. `python -c "import RNS, inspect; print(inspect.signature(RNS.Destination.register_request_handler))"`.

---

## Структура файлов

**Создаются (ApiRgRPC):**
- `rns-engine/proto/device_control.proto` — вендорная копия контракта.
- `rns-engine/proto/__init__.py`, `device_control_pb2.py`, `device_control_pb2_grpc.py` — сгенерированные стабы.
- `rns-engine/bridge/__init__.py`
- `rns-engine/bridge/bridge.py` — RNS-приёмник + диспетчер команды.
- `rns-engine/bridge/grpc_backend.py` — вызов локального gRPC `SendCommand`.
- `rns-engine/bridge/run_bridge.py` — точка входа (CLI).
- `rns-engine/tests/__init__.py`
- `rns-engine/tests/test_rns_roundtrip.py` — loopback round-trip по `TCPInterface`.
- `rns-engine/tests/test_grpc_backend.py` — мост↔gRPC c фейковым сервером.

**Создаются (UDP_gRPC_COM_Lite):**
- `reticulum_transport/__init__.py`
- `reticulum_transport/client.py` — `ReticulumTransport` (отправитель).
- `test4all/test_reticulum_transport.py` — тест отправителя против локального моста.

**Изменяются (UDP_gRPC_COM_Lite):**
- CLI-точка, где живёт `send` (определить на шаге Task 4; кандидаты:
  `home_automation/cli.py` или `remote_cli/dispatcher.py`) — добавить
  переключатель протокола `tcp|reticulum` и ветку на `ReticulumTransport`.

---

## Task 1: Вендоринг прото и генерация стабов в ApiRgRPC

**Files:**
- Create: `rns-engine/proto/device_control.proto` (копия из UDP_gRPC_COM_Lite)
- Create (generated): `rns-engine/proto/device_control_pb2.py`, `rns-engine/proto/device_control_pb2_grpc.py`, `rns-engine/proto/__init__.py`
- Modify: `rns-engine/requirements.txt`
- Test: `rns-engine/tests/test_proto_import.py`

- [ ] **Step 1: Скопировать прото и добавить зависимости**

```bash
mkdir -p rns-engine/proto rns-engine/tests
cp ../../ProjectPython/UDP_gRPC_COM_Lite/device_control.proto rns-engine/proto/device_control.proto
printf '' > rns-engine/proto/__init__.py
printf '' > rns-engine/tests/__init__.py
```

Добавить в конец `rns-engine/requirements.txt`:

```
grpcio>=1.60.0
grpcio-tools>=1.60.0
protobuf>=4.25.0
```

- [ ] **Step 2: Сгенерировать стабы**

Run:
```bash
cd rns-engine
python -m grpc_tools.protoc -Iproto --python_out=proto --grpc_python_out=proto proto/device_control.proto
```
Expected: появились `proto/device_control_pb2.py` и `proto/device_control_pb2_grpc.py`.

> Если импорт `device_control_pb2_grpc` падает на `import device_control_pb2`,
> поправь его на относительный: `from . import device_control_pb2` (известная
> особенность grpc-генерации внутри пакета).

- [ ] **Step 3: Написать падающий тест импорта/сериализации**

`rns-engine/tests/test_proto_import.py`:
```python
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
```

- [ ] **Step 4: Запустить тест**

Run: `cd rns-engine && python -m pytest tests/test_proto_import.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add rns-engine/proto rns-engine/tests/test_proto_import.py rns-engine/tests/__init__.py rns-engine/requirements.txt
git commit -m "feat(bridge): vendor device_control proto + python stubs"
```

---

## Task 2: RNS round-trip ядро по TCPInterface (мост + loopback-тест, gRPC застаблен)

Самая важная задача — доказывает Reticulum-доставку прото независимо от gRPC.

**Files:**
- Create: `rns-engine/bridge/__init__.py`, `rns-engine/bridge/bridge.py`
- Test: `rns-engine/tests/test_rns_roundtrip.py`

- [ ] **Step 1: Написать падающий loopback-тест**

`rns-engine/tests/test_rns_roundtrip.py` — поднимает мост и тест-клиента в одном процессе через общий `TCPInterface` на `localhost`, гоняет round-trip:
```python
import os, time, tempfile, threading
import RNS
from proto import device_control_pb2 as pb
from bridge.bridge import DeviceControlBridge, APP_NAME, ASPECTS, REQUEST_PATH

RNS_CONFIG = """
[reticulum]
  enable_transport = No
  share_instance = No
[interfaces]
  [[TCPServer]]
    type = TCPServerInterface
    listen_ip = 127.0.0.1
    listen_port = 4242
  [[TCPClientLoopback]]
    type = TCPClientInterface
    target_host = 127.0.0.1
    target_port = 4242
"""


def _make_config(tmp):
    os.makedirs(tmp, exist_ok=True)
    with open(os.path.join(tmp, "config"), "w") as f:
        f.write(RNS_CONFIG)
    return tmp


def test_command_roundtrip_over_tcp():
    tmp = tempfile.mkdtemp()
    _make_config(tmp)

    # Застабленный обработчик команды: эхо device_id обратно в message.
    def handler(req: pb.CommandRequest) -> pb.CommandResponse:
        return pb.CommandResponse(
            status=pb.CommandResponse.SUCCESS,
            message=f"echo:{req.device_id}",
        )

    bridge = DeviceControlBridge(configdir=tmp, storagepath=tmp, handler=handler)
    bridge.start()
    time.sleep(2)  # дать интерфейсам подняться

    result = {"resp": None}
    done = threading.Event()

    def on_response(receipt):
        resp = pb.CommandResponse()
        resp.ParseFromString(receipt.response)
        result["resp"] = resp
        done.set()

    # Клиент: дойти до Destination моста и сделать request.
    dest_hash = bridge.destination.hash
    if not RNS.Transport.has_path(dest_hash):
        RNS.Transport.request_path(dest_hash)
        deadline = time.time() + 15
        while not RNS.Transport.has_path(dest_hash) and time.time() < deadline:
            time.sleep(0.1)
    server_identity = RNS.Identity.recall(dest_hash)
    out_dest = RNS.Destination(
        server_identity, RNS.Destination.OUT, RNS.Destination.SINGLE,
        APP_NAME, *ASPECTS,
    )
    link = RNS.Link(out_dest)
    deadline = time.time() + 15
    while link.status != RNS.Link.ACTIVE and time.time() < deadline:
        time.sleep(0.1)
    assert link.status == RNS.Link.ACTIVE, "link did not activate"

    req = pb.CommandRequest(device_id="bu_led_status")
    link.request(REQUEST_PATH, data=req.SerializeToString(),
                 response_callback=on_response,
                 failed_callback=lambda r: done.set())
    assert done.wait(timeout=15), "no response within timeout"
    assert result["resp"] is not None
    assert result["resp"].message == "echo:bu_led_status"
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd rns-engine && python -m pytest tests/test_rns_roundtrip.py -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'bridge'` (мост ещё не написан).

- [ ] **Step 3: Реализовать мост (минимум для прохождения теста)**

`rns-engine/bridge/__init__.py`: пустой файл.

`rns-engine/bridge/bridge.py`:
```python
"""RNS-мост: принимает CommandRequest по Reticulum, отдаёт CommandResponse.

Транспорт абстрагирован конфигом RNS (configdir): на этапе 1 — TCPInterface,
позже — I2PInterface, без изменений в этом коде.
"""
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

        self.destination = RNS.Destination(
            self.identity, RNS.Destination.IN, RNS.Destination.SINGLE,
            APP_NAME, *ASPECTS,
        )
        self.destination.register_request_handler(
            REQUEST_PATH,
            response_generator=self._on_request,
            allow=RNS.Destination.ALLOW_ALL,
        )

    def start(self) -> None:
        # Объявляем присутствие, чтобы клиент мог найти путь к Destination.
        self.destination.announce()

    def _on_request(self, path, data, request_id, link_id, remote_identity, requested_at):
        req = pb.CommandRequest()
        try:
            req.ParseFromString(data or b"")
        except Exception as exc:  # битый прото
            resp = pb.CommandResponse(
                status=pb.CommandResponse.ERROR, message=f"bad request: {exc}")
            return resp.SerializeToString()
        resp = self._handler(req)
        return resp.SerializeToString()
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `cd rns-engine && python -m pytest tests/test_rns_roundtrip.py -v`
Expected: PASS (round-trip `echo:bu_led_status`).

> Если тест флакует на таймингах announce/path — увеличить `time.sleep`/deadline;
> это known-таймингова чувствительность RNS на холодном старте интерфейсов.

- [ ] **Step 5: Commit**

```bash
git add rns-engine/bridge rns-engine/tests/test_rns_roundtrip.py
git commit -m "feat(bridge): RNS request/response round-trip over TCPInterface (stubbed handler)"
```

---

## Task 3: Бэкенд моста — реальный локальный gRPC SendCommand

**Files:**
- Create: `rns-engine/bridge/grpc_backend.py`
- Test: `rns-engine/tests/test_grpc_backend.py`

- [ ] **Step 1: Написать падающий тест с фейковым gRPC-сервером**

`rns-engine/tests/test_grpc_backend.py`:
```python
import grpc
from concurrent import futures
from proto import device_control_pb2 as pb
from proto import device_control_pb2_grpc as pbg
from bridge.grpc_backend import GrpcCommandBackend


class _FakeService(pbg.DeviceControlServiceServicer):
    def SendCommand(self, request, context):
        return pb.CommandResponse(
            status=pb.CommandResponse.SUCCESS, message=f"grpc:{request.device_id}")


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
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd rns-engine && python -m pytest tests/test_grpc_backend.py -v`
Expected: FAIL с `ModuleNotFoundError: No module named 'bridge.grpc_backend'`.

- [ ] **Step 3: Реализовать бэкенд**

`rns-engine/bridge/grpc_backend.py`:
```python
"""Бэкенд моста: CommandRequest -> локальный gRPC SendCommand -> CommandResponse."""
import grpc

from proto import device_control_pb2 as pb
from proto import device_control_pb2_grpc as pbg


class GrpcCommandBackend:
    def __init__(self, target: str, timeout: float = 10.0):
        self._target = target
        self._timeout = timeout

    def __call__(self, req: pb.CommandRequest) -> pb.CommandResponse:
        try:
            with grpc.insecure_channel(self._target) as channel:
                stub = pbg.DeviceControlServiceStub(channel)
                return stub.SendCommand(req, timeout=self._timeout)
        except grpc.RpcError as exc:
            return pb.CommandResponse(
                status=pb.CommandResponse.ERROR,
                message=f"grpc error: {exc.code().name}",
            )
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `cd rns-engine && python -m pytest tests/test_grpc_backend.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rns-engine/bridge/grpc_backend.py rns-engine/tests/test_grpc_backend.py
git commit -m "feat(bridge): grpc backend calling DeviceControlService.SendCommand"
```

---

## Task 4: Точка входа моста + клиент-транспорт в UDP_gRPC_COM_Lite (CLI)

**Files (ApiRgRPC):**
- Create: `rns-engine/bridge/run_bridge.py`

**Files (UDP_gRPC_COM_Lite):**
- Create: `reticulum_transport/__init__.py`, `reticulum_transport/client.py`
- Test: `test4all/test_reticulum_transport.py`
- Modify: CLI-точка с `send` (определить грепом, см. Step 4)

- [ ] **Step 1: Точка входа моста (ApiRgRPC)**

`rns-engine/bridge/run_bridge.py`:
```python
"""Запуск моста на VPS: python -m bridge.run_bridge --grpc 127.0.0.1:50051 --config <dir>"""
import argparse, time
from bridge.bridge import DeviceControlBridge
from bridge.grpc_backend import GrpcCommandBackend


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--grpc", default="127.0.0.1:50051", help="локальный адрес DeviceControlService")
    p.add_argument("--config", required=True, help="configdir для RNS")
    p.add_argument("--storage", required=True, help="storagepath (identity)")
    args = p.parse_args()

    backend = GrpcCommandBackend(args.grpc)
    bridge = DeviceControlBridge(args.config, args.storage, handler=backend)
    bridge.start()
    print(f"bridge up, destination = {bridge.destination.hash.hex()}", flush=True)
    while True:
        time.sleep(60)
        bridge.start()  # периодический повторный announce


if __name__ == "__main__":
    main()
```

Commit:
```bash
git add rns-engine/bridge/run_bridge.py
git commit -m "feat(bridge): run_bridge entrypoint for VPS"
```

- [ ] **Step 2: Падающий тест отправителя (UDP_gRPC_COM_Lite)**

`test4all/test_reticulum_transport.py` — поднимает мост-эхо (как в Task 2) и проверяет, что `ReticulumTransport.send_command` возвращает `CommandResponse`:
```python
import os, time, tempfile
import RNS
from reticulum_transport.client import ReticulumTransport
# стабы прото берём из основного дерева проекта
import device_control_pb2 as pb  # noqa: ссылка на сгенерированные стабы проекта

RNS_CONFIG = """
[reticulum]
  enable_transport = No
  share_instance = No
[interfaces]
  [[TCPClient]]
    type = TCPClientInterface
    target_host = 127.0.0.1
    target_port = 4242
"""


def test_send_command_returns_response(bridge_fixture):
    tmp = tempfile.mkdtemp()
    with open(os.path.join(tmp, "config"), "w") as f:
        f.write(RNS_CONFIG)
    transport = ReticulumTransport(configdir=tmp, storagepath=tmp,
                                   bridge_hash_hex=bridge_fixture.dest_hash_hex)
    resp = transport.send_command(pb.CommandRequest(device_id="bu_led_status"))
    assert resp.status == pb.CommandResponse.SUCCESS
```

> `bridge_fixture` — pytest-фикстура, поднимающая эхо-мост на `127.0.0.1:4242`
> (TCPServerInterface) и отдающая `dest_hash_hex`. Реализовать в
> `test4all/conftest.py`, переиспользовав `DeviceControlBridge` из ApiRgRPC
> (через `sys.path` к `rns-engine`) ИЛИ скопировав минимальный эхо-мост в фикстуру.
> Решение о копии vs импорте принять при реализации (кросс-репо импорт — нежелателен).

- [ ] **Step 3: Реализовать `ReticulumTransport`**

`reticulum_transport/client.py`:
```python
"""Клиент-транспорт: CommandRequest -> RNS.Link.request -> CommandResponse.

Соглашения совпадают с мостом ApiRgRPC: APP_NAME/ASPECTS/REQUEST_PATH.
Транспорт (TCP/I2P) задаётся конфигом RNS (configdir).
"""
import time, threading
import RNS
import device_control_pb2 as pb

APP_NAME = "apirgrpc"
ASPECTS = ("bridge", "devicecontrol")
REQUEST_PATH = "/device_control"


class ReticulumTransport:
    def __init__(self, configdir, storagepath, bridge_hash_hex, timeout=20.0):
        self.timeout = timeout
        self.bridge_hash = bytes.fromhex(bridge_hash_hex)
        self.reticulum = RNS.Reticulum(configdir=configdir)

    def _ensure_path(self):
        if not RNS.Transport.has_path(self.bridge_hash):
            RNS.Transport.request_path(self.bridge_hash)
            deadline = time.time() + self.timeout
            while not RNS.Transport.has_path(self.bridge_hash) and time.time() < deadline:
                time.sleep(0.1)
        if not RNS.Transport.has_path(self.bridge_hash):
            raise TimeoutError("no path to bridge")

    def send_command(self, req: pb.CommandRequest) -> pb.CommandResponse:
        self._ensure_path()
        identity = RNS.Identity.recall(self.bridge_hash)
        dest = RNS.Destination(identity, RNS.Destination.OUT,
                               RNS.Destination.SINGLE, APP_NAME, *ASPECTS)
        link = RNS.Link(dest)
        deadline = time.time() + self.timeout
        while link.status != RNS.Link.ACTIVE and time.time() < deadline:
            time.sleep(0.1)
        if link.status != RNS.Link.ACTIVE:
            raise TimeoutError("link not active")

        result, done = {}, threading.Event()

        def on_response(receipt):
            resp = pb.CommandResponse()
            resp.ParseFromString(receipt.response)
            result["resp"] = resp
            done.set()

        link.request(REQUEST_PATH, data=req.SerializeToString(),
                     response_callback=on_response,
                     failed_callback=lambda r: done.set())
        if not done.wait(timeout=self.timeout) or "resp" not in result:
            raise TimeoutError("no response from bridge")
        return result["resp"]
```

`reticulum_transport/__init__.py`:
```python
from .client import ReticulumTransport  # noqa: F401
```

- [ ] **Step 4: Подключить переключатель протокола к существующему `send`**

Найти CLI-точку команды `send`:
```bash
grep -rnE "def .*send|\"send\"|'send'|add_parser\(.?send" --include=*.py home_automation remote_cli | grep -vE "venv|_pb2"
```
В найденном диспетчере добавить опцию протокола (`tcp` по умолчанию | `reticulum`)
и ветку: при `reticulum` строить `CommandRequest` из тех же аргументов `send` и
вызывать `ReticulumTransport(...).send_command(req)` вместо существующего
gRPC/TCP-вызова. **Существующая `tcp`-ветка не меняется.** Конкретные строки
зафиксировать при реализации (зависит от найденного файла) и показать diff в ревью.

- [ ] **Step 5: Запустить тест отправителя**

Run (UDP_gRPC_COM_Lite): `python -m pytest test4all/test_reticulum_transport.py -v`
Expected: PASS.

- [ ] **Step 6: Commit (UDP_gRPC_COM_Lite)**

```bash
git add reticulum_transport test4all/test_reticulum_transport.py test4all/conftest.py
# + изменённый CLI-файл
git commit -m "feat(cli): reticulum protocol switch + ReticulumTransport for send"
```

---

## Task 5: Сквозная проверка на localhost + обновление статуса

**Files:**
- Modify: `RETICULUM_TRANSPORT.md` (раздел 7 — чек-лист)

- [ ] **Step 1: Запустить реальный gRPC DeviceControlService UDP_gRPC_COM_Lite локально**

(по README проекта — `home_automation/server.py` или соответствующий сервер,
слушающий `SendCommand`). Зафиксировать его адрес, напр. `127.0.0.1:50051`.

- [ ] **Step 2: Запустить мост против реального gRPC**

```bash
cd rns-engine
python -m bridge.run_bridge --grpc 127.0.0.1:50051 --config ./_rnscfg --storage ./_rnsdata
# скопировать напечатанный destination hash
```

- [ ] **Step 3: Отправить команду из CLI по reticulum**

В UDP_gRPC_COM_Lite CLI выбрать `protocol reticulum`, выполнить `send …`
с тем же destination hash моста. Ожидание: приходит `CommandResponse` от
реального сервиса (не эхо).

- [ ] **Step 4: Отметить статус**

В `RETICULUM_TRANSPORT.md` раздел 7, Этап 1 — проставить ✅ выполненным пунктам
(прото-стабы, мост, бэкенд, ReticulumTransport, loopback-тест, локальный e2e).

- [ ] **Step 5: Commit + push**

```bash
# ApiRgRPC
git add RETICULUM_TRANSPORT.md
git commit -m "docs: stage 1 status — reticulum round-trip green on localhost"
git push origin main
# UDP_gRPC_COM_Lite — отдельный push в своём репозитории
```

---

## Замечания по исполнению

- **Кросс-репо.** План затрагивает два репозитория (ApiRgRPC + UDP_gRPC_COM_Lite),
  у них **разные GitHub-аккаунты** (`kureinmaxim` / `maximkurein` — проверить
  remote перед push). Коммиты и пуши — раздельные, в свои репозитории.
- **Не трогаем:** серверы BU/BZ/BF, существующий gRPC/TCP `send`-путь (ветка `tcp`).
- **I2P (этап 3)** не входит в этот план: после зелёного этапа 1 меняется только
  секция интерфейса в конфиге RNS (`TCPInterface` → `I2PInterface`), код задач
  1–4 не меняется.
- **Артефакты** (`_rnscfg/`, `_rnsdata/`, identity-файлы) добавить в `.gitignore`
  обоих репозиториев перед коммитами.
