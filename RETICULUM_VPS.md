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
| 3 — I2P | ✅ e2e зелёный (2026-06-26) через нативные туннели i2pd (путь 2, см. §12); ⬜ закрыть публичный TCP-порт (§12.4) |
| 4 — device-control в GUI ApiRgRPC | ⬜ не начато |

---

## 10. Следующие шаги (живой раздел)

**Этап 3 — I2P (e2e ✅, путь 2 — нативные туннели i2pd):**
- ✅ i2pd на **VPS** (2.45.1) + **server-туннель** `ha-bridge` → b32
  `x4utehodm…b32.i2p` (§12.2); на **Mac** i2pd 2.60.0 + **client-туннель** (§12.3-B).
- ✅ Стрим этапа 2 прошёл поверх I2P; hash моста `12bbf2cd…` тот же.
- ❌ Путь 1 (RNS `I2PInterface`/SAM) отброшен — не поднимается, см. §12.5.
- ⬜ i2pd на **Windows** (для exe-клиента; блокирует Defender — но путь 2 без SAM).
- ⬜ Закрыть публичный TCP-порт 50061 наружу (§12.4).

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

> Этот раздел — точка возобновления работы. Обновлено 2026-06-26 (сессия macOS):
> этап 2 ✅ в проде, **этап 3 — I2P e2e ✅ зелёный** через нативные туннели i2pd
> (путь 2). Встроенный RNS `I2PInterface` (путь 1) отброшен — не работает, см. 12.5.

### 12.0 Итог сессии (что сделано на Mac)
- ✅ `git pull` обоих репо (`ApiRgRPC`, `UDP_gRPC_COM_Lite`).
- ✅ **Режим A (прямой TCP)** с Mac — round-trip/стрим зелёные (5 событий).
- ✅ **Этап 3, I2P e2e** — стрим этапа 2 прошёл **поверх I2P** через путь 2.
- Архитектура пути 2 (RNS вообще не трогает SAM):
  `RNS ↔ TCP ↔ i2pd client-туннель ↔ I2P ↔ i2pd server-туннель ↔ TCP ↔ bridge`.

### 12.1 Что крутится на VPS
- **Мост слушает `0.0.0.0:50061` (режим A)** — TCP-путь рабочий, доступен с любого
  ПК по публичному IP `138.226.221.219`. Хэш моста (транспортно-независим):
  **`12bbf2cd888546cf78bc76112e0b3bbe`**.
- i2pd `2.45.1`, `Network status: OK`, транспортный порт `15613`, SAM `127.0.0.1:7656`,
  `bandwidth = P`.
- **Server-туннель i2pd** `/etc/i2pd/tunnels.d/ha-bridge.conf` заворачивает
  `127.0.0.1:50061` (мостовой `TCPServerInterface`) в стабильный I2P-destination
  (ключи `ha-bridge.dat`). Это и даёт b32 (12.2).
- RNS-секция `[[I2P]]` из конфига моста **удалена** (2026-06-26 cleanup) — она не
  работала и спамила `SAM went offline` каждые ~26 мин (см. 12.5). Путь 2 её не
  использует. Мост несёт только `TCPServerInterface 0.0.0.0:50061` (его и заворачивает
  server-туннель i2pd). Также сняты отладочные `loglevel = 4`→`3` и drop-in
  `PYTHONUNBUFFERED`.
- **Оба транспорта верифицированы зелёными после чистки (2026-06-26):** прямой TCP
  (`client_rns`) и I2P путь 2 (`client_rns_i2p`) — стрим этапа 2 даёт события на обоих.

### 12.2 b32 моста (server-туннель i2pd)
**b32 моста = `x4utehodm3nezw5xb72nrdzhx3jestb2yqjdnbn46ljgzqd53aza.b32.i2p`** (порт `:50061`).
Проверить/получить заново на VPS:
```bash
curl -s "http://127.0.0.1:7070/?page=i2p_tunnels" | sed 's/<[^>]*>/ /g' | grep -iE 'ha-bridge|\.b32'
```
Стабилен между рестартами (ключи `ha-bridge.dat`).

Конфиг server-туннеля на VPS (`/etc/i2pd/tunnels.d/ha-bridge.conf`):
```ini
[ha-bridge]
type = server
host = 127.0.0.1
port = 50061
keys = ha-bridge.dat
inbound.length = 2
outbound.length = 2
inbound.quantity = 3
outbound.quantity = 3
```

### 12.3 Клиент на macOS — оба пути рабочие
Репозитории: `ApiRgRPC` (доки) и `UDP_gRPC_COM_Lite`
(`~/Project/ProjectPython/UDP_gRPC_COM_Lite`, venv `.venv/bin/python3`).
> ⚠️ В venv не было `rns`/`lxmf` (в `requirements.txt` не закреплены) — поставить:
> `.venv/bin/pip install rns lxmf` (стоят `rns 1.3.5`, `lxmf 1.0.1`).

**A) Прямой TCP** — `~/Project/client_rns/config`:
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
```bash
.venv/bin/python3 -m reticulum_transport.subscribe_demo \
  --bridge-hash 12bbf2cd888546cf78bc76112e0b3bbe --rns-config ~/Project/client_rns --block BU --max 5
```
Ожидание: 5 событий `mi_th_sensor`, `received 5 events`.

**B) По I2P (путь 2)** — i2pd + client-туннель, RNS ходит по TCP на localhost:
```bash
brew install i2pd            # 2.60.0
brew services start i2pd
```
В `$(brew --prefix)/etc/i2pd/tunnels.conf` дописать client-туннель:
```ini
[ha-bridge-client]
type = client
address = 127.0.0.1
port = 50061
destination = x4utehodm3nezw5xb72nrdzhx3jestb2yqjdnbn46ljgzqd53aza.b32.i2p
destinationport = 50061
keys = ha-bridge-client.dat
```
`brew services restart i2pd` → поднимется local listener `127.0.0.1:50061`.
> SAM на Mac **не нужен** (путь 2 не использует SAM). `Network status: Firewalled`
> у клиента — норма (нужны только исходящие туннели). Свежий i2pd прогревается
> 3–7 мин (reseed + туннели), первый коннект медленный.

Отдельный RNS-конфиг `~/Project/client_rns_i2p/config` (route A не трогаем):
```ini
[reticulum]
  enable_transport = No
  share_instance = No
[interfaces]
  [[TCP Client Interface]]
    type = TCPClientInterface
    interface_enabled = yes
    target_host = 127.0.0.1
    target_port = 50061
```
```bash
.venv/bin/python3 -m reticulum_transport.subscribe_demo \
  --bridge-hash 12bbf2cd888546cf78bc76112e0b3bbe --rns-config ~/Project/client_rns_i2p --block BU --max 5
```
Команда и hash моста **те же** — отличается только `--rns-config` (через какой
конфиг RNS подключаться: прямой TCP или localhost-туннель i2pd). ✅ Проверено зелёным.

### 12.4 Финал этапа 3 (закрыть TCP наружу)
После того как I2P-путь устраивает по стабильности:
- Закрыть публичный порт, оставив мост слушать на `127.0.0.1` (i2pd server-туннель
  всё равно ходит на `127.0.0.1:50061`):
  `iptables -D INPUT -p tcp --dport 50061 -j ACCEPT` (+ при желании
  `sed -i 's/listen_ip = 0.0.0.0/listen_ip = 127.0.0.1/' …/rns/config; systemctl restart ha-reticulum-bridge`).
- Обновить чек-листы: [I2P.md](I2P.md) §7, [RETICULUM_TRANSPORT.md](RETICULUM_TRANSPORT.md) §7.

### 12.5 Почему отказались от RNS `I2PInterface` (путь 1)
Встроенный `type = I2PInterface` (bundled i2plib через SAM) на этом стеке
**не поднимается**: endpoint висит в «Bringing up I2P endpoint» по ~26 мин и падает
с `[Errno 9] Bad file descriptor` → `SAM API went offline` → `Resetting I2P tunnel`
(SAM-control-сокет рвётся, i2pd сносит туннели destination → leaseset не публикуется).
Воспроизводится при здоровом i2pd (`Network status: OK`, SAM 7656 жив) и
актуальных `RNS 1.3.5` / Python 3.11. Лечения версией нет (RNS уже последний).
**Вывод:** I2P делаем нативными туннелями i2pd (путь 2) — RNS общается обычным TCP
с локальным туннелем, i2plib не задействован.

---

*Серверная карта стека ApiRgRPC↔HA поверх Reticulum. Точные значения,
помеченные ⚠️, заполняются по выводу диагностики с VPS (§10).*
