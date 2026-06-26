# RETICULUM_VPS.md — серверная инсталляция Reticulum-стека (как развёрнуто и работает)

Живой документ: **как сейчас установлен и работает** обмен прото-сообщениями
поверх Reticulum на боевом VPS, понятная архитектура, серверные сервисы/порты/пути,
клиентская сторона и **следующие шаги**. Дополняет:
[RETICULUM_TRANSPORT.md](RETICULUM_TRANSPORT.md) (дизайн/этапы/статус),
[RETICULUM_TESTING.md](RETICULUM_TESTING.md) (как тестировать),
[I2P.md](I2P.md) (транспорт этапа 3).

> Документ ведётся по ходу проекта. При изменениях на сервере (сервисы, порты,
> хэш моста, переход на I2P) — обновляйте разделы 4, 7 и 9.
> Статус: **этапы 1–2 завершены и проверены в проде (2026-06-26).**

---

## 1. Назначение стека

Доставлять команды/события `device_control.proto` на кастомный HA-сервер
**вторым транспортом — поверх Reticulum**, в дополнение к существующему TCP/gRPC.
На VPS живёт **RNS-мост**: принимает запросы по Reticulum-линку и проксирует их в
локальный gRPC/UDP HA-стек. Клиент (сейчас CLI `UDP_gRPC_COM_Lite`, позже GUI
ApiRgRPC) шлёт прото по `RNS.Link`.

Подробный «зачем» и рамки — [RETICULUM_TRANSPORT.md](RETICULUM_TRANSPORT.md) §1.

---

## 2. Хост и сеть

| Параметр | Значение |
|---|---|
| Хост | `vps44208.hosted-by-eurohoster.org` |
| Публичный IP (endpoint) | `138.226.221.219` |
| Tailscale IP | `100.64.0.11` (`vps44208-…`) |
| OS | Linux (Debian/Ubuntu), systemd |
| Firewall | **нет `ufw`** — правила через `iptables` |
| Hash моста (RNS destination) | `12bbf2cd888546cf78bc76112e0b3bbe` (стабилен между рестартами; меняется только при пересоздании RNS-identity) |

---

## 3. Архитектура

```
            КЛИЕНТ (Windows / Mac)                       VPS  (vps44208, 138.226.221.219)
 ┌──────────────────────────────────┐        ┌────────────────────────────────────────────────┐
 │ CLI UDP_gRPC_COM_Lite             │        │  systemd                                       │
 │   reticulum_transport             │        │                                                │
 │   ├ device send  → /device_control│        │  ha-reticulum-bridge  (RNS-мост)               │
 │   ├ send --hex   → /udp_raw       │        │    RNS.Destination IN/SINGLE                    │
 │   └ subscribe_demo → стрим (Channel)│      │    listen 0.0.0.0:50061  (TCPServerInterface)  │
 │   RNS-конфиг: C:\Project\client_rns│       │    hash 12bbf2cd…                              │
 └───────────────┬──────────────────┘        │      │                                         │
                 │  RNS.Link (proto bytes,                │ /device_control → gRPC 127.0.0.1:50055 │
                 │  всё шифровано Reticulum)   │      │  /udp_raw        → UDP  127.0.0.1:50056 │
                 │                             │      │  стрим           ← gRPC SubscribeEvents │
                 ▼                             │      ▼                                         │
        TCP :50061 (этап 1–2)  ───────────────┼─►  ha-stub-grpc  127.0.0.1:50055  (HA-заглушка)│
        (этап 3: I2P, порт наружу не нужен)    │       stub_server.py: SendCommand+SubscribeEvents│
                                               │    ha-stub-udp   127.0.0.1:50056  (UDP-заглушка)│
                                               │    shskm-bu      :50051  (реальный BU, опц.)    │
                                               └────────────────────────────────────────────────┘
```

Ключевая идея: **приложение транспортно-агностично**. Сейчас под мостом
`TCPServerInterface` (этапы 1–2). На этапе 3 меняется **только секция интерфейса
в конфиге RNS** на `I2PInterface` — код моста и клиента не трогаем
([I2P.md](I2P.md), [RETICULUM_TRANSPORT.md](RETICULUM_TRANSPORT.md) §10).

---

## 4. systemd-сервисы

Снимок состояния (`systemctl is-active …` — все `active` на 2026-06-26):

| Сервис | Слушает | Назначение | ExecStart / WorkingDirectory |
|---|---|---|---|
| `ha-reticulum-bridge` | `0.0.0.0:50061` (TCP, режим A) | RNS-мост: приём Reticulum-запросов, форвард в gRPC/UDP | `python -m bridge.run_bridge --grpc 127.0.0.1:50055 --udp-target 127.0.0.1:50056 --config /opt/TelegramOnly/ha_stack/rns --storage /opt/TelegramOnly/ha_stack/.rnsdata`; WD=`/opt/TelegramOnly/ha_stack` |
| `ha-stub-grpc` | `127.0.0.1:50055` (TCP) | HA-заглушка gRPC `DeviceControlService`: `SendCommand` + `SubscribeEvents` | `python /opt/TelegramOnly/ha_stack/stub_server.py --listen 127.0.0.1:50055`; WD=`/opt/TelegramOnly/ha_stack` |
| `ha-stub-udp` | `127.0.0.1:50056` (UDP) | UDP-заглушка для пути `/udp_raw` | `python /opt/TelegramOnly/ha_stack/udp_stub.py --listen-ip 127.0.0.1 --listen-port 50056`; WD=`/opt/TelegramOnly/ha_stack` |
| `shskm-bu` | `:50051` | реальный блок BU (опц., для боевого `/udp_raw`) | см. UDP_gRPC_COM_Lite |
| `remote-cli` | `:18090` | операторский gRPC-канал (отдельный путь, не Reticulum) | поднимается отдельно; токен в `/etc/shskm/remote-cli.env` |

> Мост печатает при старте (виден в `journalctl -u ha-reticulum-bridge`):
> `bridge up, destination = 12bbf2cd…` · `grpc backend = 127.0.0.1:50055` ·
> `event stream /subscribe enabled (RNS Channel)` · `udp path /udp_raw enabled -> 127.0.0.1:50056`.

---

## 5. Пути на диске (VPS)

| Что | Путь |
|---|---|
| Корень HA-стека | `/opt/TelegramOnly/ha_stack/` |
| Python venv стека | `/opt/TelegramOnly/ha_stack/.venv/` (все сервисы запускаются этим интерпретатором) |
| gRPC-заглушка HA | `/opt/TelegramOnly/ha_stack/stub_server.py` (`SendCommand` + `SubscribeEvents`) |
| UDP-заглушка | `/opt/TelegramOnly/ha_stack/udp_stub.py` |
| Код моста | `/opt/TelegramOnly/ha_stack/bridge/` (пакет `bridge.run_bridge`; вендоринг `rns-engine/bridge/` из ApiRgRPC) |
| RNS-конфиг моста | `/opt/TelegramOnly/ha_stack/rns/config` |
| RNS storage/identity моста | `/opt/TelegramOnly/ha_stack/.rnsdata/` (хранит стабильную identity → hash) |
| Токен remote-cli | `/etc/shskm/remote-cli.env` (права `600`) |

**Версии в `ha_stack/.venv` (2026-06-26):** Python `3.11.2`, `rns 1.3.5`,
`grpcio 1.81.1`, `protobuf 7.35.1`.

---

## 6. RNS-конфиг моста (текущее состояние)

`/opt/TelegramOnly/ha_stack/rns/config` — секция интерфейса (**режим A**, открыт
наружу для теста 2026-06-26):
```ini
[reticulum]
  enable_transport = No
[interfaces]
  [[TCP Server Interface]]
    type = TCPServerInterface
    interface_enabled = yes
    listen_ip = 0.0.0.0          # ⚠️ режим A: порт 50061 открыт в интернет
    listen_port = 50061
```

**Два режима связи клиент↔мост** (детали — [RETICULUM_TESTING.md](RETICULUM_TESTING.md) §1):
- **Режим A (прямой):** `listen_ip = 0.0.0.0` + `iptables -I INPUT -p tcp --dport 50061 -j ACCEPT`; клиент идёт на публичный IP. Надёжно для теста, но порт открыт наружу.
- **Режим B (SSH-туннель):** `listen_ip = 127.0.0.1`; клиент через `ssh -N -L 127.0.0.1:50061:127.0.0.1:50061`. Безопаснее, но на Eurohoster туннель флапал.

> Трафик Reticulum шифрован end-to-end, gRPC/UDP-заглушки остаются на localhost
> VPS. Тем не менее **для боевого режима порт 50061 наружу держать не нужно** —
> вернуть `127.0.0.1` (режим B) или перейти на **I2P (этап 3)**, где публичный
> TCP-порт не требуется вовсе.

---

## 7. Потоки данных (что работает сейчас)

1. **`/device_control` (unary, прото)** — этап 1 ✅
   `device send` → `RNS.Link.request("/device_control", CommandRequest)` → мост
   декодирует → локальный gRPC `SendCommand` (:50055) → `CommandResponse` обратно
   по Reticulum. Проверено в проде: `mi_th_sensor: T=23.5C H=45%`.
2. **`/udp_raw` (unary, сырой UDP)** — этап 1 ✅
   `send --hex …` → `RNS.Link.request("/udp_raw", bytes)` → мост форвардит UDP-ом
   на `--udp-target` (сейчас заглушка :50056; для реального BU — перенацелить на
   прокси→BU, см. [VPS_TEST.md](../ProjectPython/UDP_gRPC_COM_Lite/rust_server/VPS_TEST.md) §5.4).
3. **Стрим событий (`RNS.Channel`)** — этап 2 ✅ (**проверено в проде 2026-06-26**)
   `subscribe_demo` открывает Link, шлёт `SubscribeMessage` → мост поднимает Channel,
   локально вызывает gRPC `SubscribeEvents` (:50055) и форвардит каждый `DeviceEvent`
   обратно `DeviceEventMessage`'ами. Результат: 5 событий `mi_th_sensor`
   (`T=23.5→23.9C H=45%`), `received 5 events`.

---

## 8. Клиентская сторона: зачем `C:\Project\client_rns\config` и как будет с exe

### 8.1 Зачем нужен `C:\Project\client_rns\config` сейчас
Это **отдельный, ручной RNS-конфиг для CLI-клиента** `UDP_gRPC_COM_Lite` на время
разработки/тестов. Reticulum при инициализации читает каталог конфига (`configdir`)
и из него понимает, **через какой интерфейс** идти в сеть. Для клиента это
`TCPClientInterface`, нацеленный на мост:
```ini
[reticulum]
  enable_transport = No
  share_instance = No
[interfaces]
  [[TCP Client Interface]]
    type = TCPClientInterface
    interface_enabled = yes
    target_host = 138.226.221.219   # публичный IP VPS (режим A); 127.0.0.1 для туннеля (режим B)
    target_port = 50061
```
- `--rns-config C:/Project/client_rns` передаётся в `subscribe_demo` / `device send`
  и попадает в `RNS.Reticulum(configdir=…)`.
- В каталоге также лежит `storage/` — RNS хранит там identity/ключи клиента и
  кэш путей.
- **Хэш моста** (`--bridge-hash 12bbf2cd…`) передаётся отдельно (out-of-band, как
  принято в Reticulum) — это *кому* слать; конфиг — *как/через что* идти в сеть.

Иначе говоря: **конфиг = выбор транспорта и точки входа в сеть; bridge-hash =
адрес назначения.** Меняя только секцию интерфейса в этом конфиге (TCP → I2P), тот
же клиент пойдёт через I2P без изменения кода.

### 8.2 Как это будет работать, когда соберёшь exe ApiRgRPC
В собранном десктоп-приложении **ручной `client_rns` не понадобится** — им управляет
само приложение:
- Tauri-оболочка запускает Python-движок-сайдкар и **сама задаёт ему `configdir`**
  в каталоге данных приложения. Уже сейчас в [engine.rs](tauri-app/src-tauri/src/engine.rs)
  движок стартует с `--config <app_data_dir>/reticulum` и `--store <app_data_dir>/store`
  (на Windows `app_data_dir` ≈ `%APPDATA%\<bundle-id>\`).
- То есть RNS-конфиг и storage будут жить **внутри профиля приложения**, создаваться
  и редактироваться программно (а не руками в `C:\Project\client_rns`).
- На **этапе 4** в этот движок добавится device-control / `ReticulumTransport`
  (перенос паттерна отправителя из CLI). Пользователь в GUI задаёт `bridge-hash` и
  (для режима A) адрес моста — приложение прописывает их в свой управляемый конфиг.
- Переключение TCP→I2P для пользователя exe будет **настройкой**, а не правкой
  файла: приложение сгенерирует нужную секцию интерфейса.

**Вывод:** `C:\Project\client_rns\config` — это *временный тест-артефакт стадии
разработки*. В продуктовом exe его роль берёт на себя управляемый приложением
конфиг в каталоге данных. Контракт (configdir + bridge-hash) тот же — меняется
лишь то, *кто* создаёт конфиг: разработчик вручную → приложение автоматически.

---

## 9. Текущий статус

| Этап | Статус |
|---|---|
| 1 — PoC round-trip (`/device_control`, `/udp_raw`) по TCP | ✅ в проде |
| 2 — стрим `DeviceEvent` по `RNS.Channel` | ✅ в проде (2026-06-26) |
| 3 — I2P (убрать публичный порт) | 🟦 в работе: i2pd на VPS поднят (2.45.1, SAM 7656) ([I2P.md](I2P.md) §7) |
| 4 — device-control в GUI ApiRgRPC | ⬜ не начато |

---

## 10. Следующие шаги (живой раздел)

**Этап 3 — I2P (в работе):**
- ✅ i2pd + SAM (7656) на **VPS** (2.45.1); ⬜ i2pd на **Windows** (блокирует Defender).
- ✅ `I2PInterface` добавлен в конфиг моста **рядом** с TCP (не заменяя пока);
  загружается, подключается к SAM, создаёт destination.
- 🟦 Дождаться готовности I2P-endpoint и **b32 моста** (свежий i2pd прогревается
  30–60 мин; поднята полоса `bandwidth = P`). Подробности и грабли — [I2P.md](I2P.md) §7, §7.1.
- ⬜ На клиенте — `I2PInterface` + `peers = <b32 моста>` в `C:\Project\client_rns\config`.
- ⬜ Прогнать round-trip и стрим поверх I2P; убрать TCP-секцию, закрыть публичный порт 50061.

> На время этапа 3 у моста подняты: `loglevel = 4` (чтобы видеть b32) и drop-in
> `PYTHONUNBUFFERED=1` (чтобы лог RNS шёл в journal). См. [I2P.md](I2P.md) §7.1.

**Эксплуатация / приведение в боевой вид:**
- ⬜ Вернуть мост на `127.0.0.1` (режим B) или перейти на I2P — закрыть `0.0.0.0:50061`.
- ⬜ Оформить токены/доступы боевыми значениями (remote-cli).

**Этап 4 — продуктовый клиент:** перенос `ReticulumTransport` в Tauri-движок ApiRgRPC.

**Что нужно дозаполнить в этом документе (с VPS):** статус i2pd (после установки на
этапе 3) и b32-адрес моста. Остальные факты (ExecStart, версии, пути) — заполнены.

---

## 11. Эксплуатация (шпаргалка команд, 🛰️ на VPS)

```bash
# Статус сервисов
systemctl is-active ha-reticulum-bridge ha-stub-grpc ha-stub-udp        # active ×3

# Что слушает
ss -tlnp | grep -E ':50061|:50055|:50051|:18090'; ss -ulnp | grep ':50056'

# Хэш моста и режим стрима
journalctl -u ha-reticulum-bridge -n 40 --no-pager | grep -E 'destination|event stream|udp path'

# Режим A (открыть наружу для теста)
sed -i 's/listen_ip = 127.0.0.1/listen_ip = 0.0.0.0/' /opt/TelegramOnly/ha_stack/rns/config
iptables -I INPUT -p tcp --dport 50061 -j ACCEPT
systemctl restart ha-reticulum-bridge

# Вернуть в боевой режим (закрыть наружу)
sed -i 's/listen_ip = 0.0.0.0/listen_ip = 127.0.0.1/' /opt/TelegramOnly/ha_stack/rns/config
iptables -D INPUT -p tcp --dport 50061 -j ACCEPT
systemctl restart ha-reticulum-bridge
```

Клиентские команды теста (🖥️ Windows) — [RETICULUM_TESTING.md](RETICULUM_TESTING.md) §2.

---

## 12. Хэндофф: продолжить с другого ПК (macOS) — снимок 2026-06-26

> Этот раздел — точка возобновления работы. Снято на момент: этап 2 ✅ в проде,
> этап 3 🟦 (i2pd на VPS поднят, ждём прогрев I2P-endpoint).

### 12.1 Что сейчас крутится на VPS (временные правки этой сессии)
- **Мост слушает `0.0.0.0:50061` (режим A)** — TCP-путь рабочий, доступен с любого
  ПК по публичному IP `138.226.221.219`. Хэш моста (транспортно-независим):
  **`12bbf2cd888546cf78bc76112e0b3bbe`**.
- В конфиг моста `/opt/TelegramOnly/ha_stack/rns/config` добавлен `I2PInterface`
  рядом с TCP; `loglevel = 4`.
- Drop-in `Environment=PYTHONUNBUFFERED=1` для `ha-reticulum-bridge` (логи RNS в journal).
- i2pd `2.45.1`, SAM `127.0.0.1:7656`, `bandwidth = P` (греется).
- **TCP-путь работает прямо сейчас** — c Mac можно сразу гонять тесты по TCP, не
  дожидаясь I2P (см. 12.3). I2P подключим, когда будет b32 (12.2).

### 12.2 Шаг 1 — забрать b32 моста (когда I2P прогреется)
🛰️ на VPS:
```bash
journalctl -u ha-reticulum-bridge --since "60 min ago" --no-pager | grep -iE 'endpoint ready|\.i2p|b32' | tail
curl -s "http://127.0.0.1:7070/" | sed 's/<[^>]*>/ /g' | grep -iE 'tunnel creation|leaseset'
curl -s "http://127.0.0.1:7070/?page=local_destinations" | sed 's/<[^>]*>/ /g' | grep -iE '\.b32\.i2p'
```
Готовность: `LeaseSets ≥ 1` + строка `endpoint ready … <b32>`. Запиши b32 сюда:
**b32 моста = `<заполнить>`**.

### 12.3 Шаг 2 — клиент на macOS
Репозитории на Mac (синхронизировать `git pull`):
- `ApiRgRPC` (этот репо, доки/мост): `git pull` в локальной копии.
- `UDP_gRPC_COM_Lite` (CLI-клиент, `~/Project/ProjectPython/UDP_gRPC_COM_Lite`,
  venv `.venv/bin/python3`).

**A) Сразу по TCP (работает уже сейчас, без i2pd):** создать `~/Project/client_rns/config`:
```ini
[reticulum]
  enable_transport = No
  share_instance = No
[interfaces]
  [[TCP Client Interface]]
    type = TCPClientInterface
    interface_enabled = yes
    target_host = 138.226.221.219
    target_port = 50061
```
Тест (стрим этапа 2) — из корня `UDP_gRPC_COM_Lite`:
```bash
.venv/bin/python3 -m reticulum_transport.subscribe_demo \
  --bridge-hash 12bbf2cd888546cf78bc76112e0b3bbe --rns-config ~/Project/client_rns --block BU --max 5
```
Ожидание: 5 событий `mi_th_sensor`, `received 5 events`.

**B) По I2P (когда есть b32):** на macOS поставить i2pd (без Defender-трений):
```bash
brew install i2pd
# включить SAM: в $(brew --prefix)/etc/i2pd/i2pd.conf секция [sam] enabled = true (порт 7656)
brew services start i2pd
# проверить: nc -z 127.0.0.1 7656  (SAM слушает)
```
Клиентский `~/Project/client_rns/config` — заменить TCP-секцию на I2P:
```ini
[reticulum]
  enable_transport = No
  share_instance = No
[interfaces]
  [[I2P]]
    type = I2PInterface
    interface_enabled = yes
    peers = <b32 моста из 12.2>
```
> Хэш моста `--bridge-hash 12bbf2cd…` **тот же** (он транспортно-независим);
> меняется только секция интерфейса + `peers`. Первый коннект по I2P медленный
> (строятся туннели 30–120 c). Команда теста — та же, что в (A).

### 12.4 Финал этапа 3 (после зелёного I2P e2e)
- Убрать TCP-секцию из конфига моста, закрыть публичный порт:
  `sed -i 's/listen_ip = 0.0.0.0/listen_ip = 127.0.0.1/' …/rns/config; iptables -D INPUT -p tcp --dport 50061 -j ACCEPT; systemctl restart ha-reticulum-bridge`
  (I2P наружу TCP не слушает — публичный порт больше не нужен).
- Обновить чек-листы: [I2P.md](I2P.md) §7, [RETICULUM_TRANSPORT.md](RETICULUM_TRANSPORT.md) §7.

---

*Серверная карта стека ApiRgRPC↔HA поверх Reticulum. Точные значения,
помеченные ⚠️, заполняются по выводу диагностики с VPS (§10).*
