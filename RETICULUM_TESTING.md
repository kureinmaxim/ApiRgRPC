# RETICULUM_TESTING.md — как тестировать Reticulum-транспорт (этапы 1–3)

Рабочая процедура e2e-теста: клиент `UDP_gRPC_COM_Lite` (Windows/macOS) ↔ HA-стек на
VPS через **Reticulum**. Зафиксировано по факту успешных прогонов: round-trip
2026-06-23 (`mi_th_sensor: T=23.5C H=45%`), стрим этапа 2 и **I2P (путь 2)** —
2026-06-26. Три транспорта связи: прямой TCP (режим A), SSH-туннель (режим B),
**I2P через нативные туннели i2pd (режим C / путь 2)** — см. §1.

> Полная серверная/клиентская карта I2P-пути и грабли — в
> [RETICULUM_VPS.md](RETICULUM_VPS.md) §12.

## 0. Что должно быть готово

**На VPS** — HA-стек развёрнут в `/opt/TelegramOnly/ha_stack/` (три systemd-сервиса;
установка/код — TelegramOnly `DEPLOY.md §6.7` + `ha_stack/`, эксплуатация — `POST_DEPLOY.md §12`).
Проверка на VPS:
```bash
systemctl is-active ha-reticulum-bridge ha-stub-grpc ha-stub-udp   # три active
ss -tlnp | grep 50061                                              # мост слушает
journalctl -u ha-reticulum-bridge -n 5 --no-pager | grep destination
#   -> bridge up, destination = <BRIDGE_HASH>   (стабилен между рестартами)
```
Запомни `<BRIDGE_HASH>` (напр. `12bbf2cd888546cf78bc76112e0b3bbe`, актуальный на 2026-06-25).
> ⚠️ Хэш меняется при пересоздании RNS-identity (переустановка `ha_stack`, удаление конфига). Всегда читай актуальный из `journalctl`.

**Для режима C (I2P)** на VPS дополнительно поднят i2pd + server-туннель `ha-bridge`:
```bash
systemctl is-active i2pd                                                      # active
curl -s "http://127.0.0.1:7070/?page=i2p_tunnels" | sed 's/<[^>]*>/ /g' | grep -i ha-bridge   # b32 моста
```

**Remote CLI gRPC сервер** — на VPS дополнительно поднят `remote_cli.server` из
`~/UDP_gRPC_COM_Lite` (Python 3.11, `.venv`, `grpcio 1.81.1`, `protobuf 6.33.6`).

Токен задаётся через `env`-переменные. Три способа запустить сервер на VPS:

**Вариант 1 — foreground (для отладки, умрёт при закрытии терминала):**
```bash
cd ~/UDP_gRPC_COM_Lite && source .venv/bin/activate
export SHSKM_REMOTE_CLI_TOKEN='change-this-token'
export SHSKM_REMOTE_CLI_REQUIRE_TOKEN=true
python -m remote_cli.server --host 0.0.0.0 --port 18090
# → Remote CLI gRPC server listening on 0.0.0.0:18090
```
Если сервер уже запущен в foreground и нужно удержать его живым без перезапуска:
```bash
# Ctrl+Z  — приостановить
bg        # перевести в фон
disown    # отвязать от сессии (выживет после закрытия Tabby)
```

**Вариант 2 — nohup (быстрый фон, лог в файл):**
```bash
cd ~/UDP_gRPC_COM_Lite && source .venv/bin/activate
export SHSKM_REMOTE_CLI_TOKEN='change-this-token'
export SHSKM_REMOTE_CLI_REQUIRE_TOKEN=true
nohup python -m remote_cli.server --host 0.0.0.0 --port 18090 \
  >> ~/UDP_gRPC_COM_Lite/logs/remote_cli.log 2>&1 &
echo $!   # запомни PID
# остановить: kill <PID>  или  pkill -f remote_cli.server
```

**Вариант 3 — systemd (надёжно, автостарт после ребута):**
```ini
# /etc/systemd/system/remote-cli.service
[Unit]
Description=Remote CLI gRPC server (UDP_gRPC_COM_Lite)
After=network.target

[Service]
WorkingDirectory=/root/UDP_gRPC_COM_Lite
Environment="SHSKM_REMOTE_CLI_TOKEN=change-this-token"
Environment="SHSKM_REMOTE_CLI_REQUIRE_TOKEN=true"
ExecStart=/root/UDP_gRPC_COM_Lite/.venv/bin/python -m remote_cli.server --host 0.0.0.0 --port 18090
Restart=on-failure
StandardOutput=append:/root/UDP_gRPC_COM_Lite/logs/remote_cli.log
StandardError=append:/root/UDP_gRPC_COM_Lite/logs/remote_cli.log

[Install]
WantedBy=multi-user.target
```
```bash
systemctl daemon-reload
systemctl enable --now remote-cli
systemctl status remote-cli
```
> ⚠️ Токен `change-this-token` — заглушка. Поменяй перед боевым использованием.

**На клиенте** — RNS-конфиг `C:\Project\client_rns\config` (см. §1).

## 1. Режимы связи клиент↔мост (A — прямой TCP, B — SSH-туннель, C — I2P)

### Режим A — прямое подключение (рабочий, для теста)
Самый надёжный для проверки (без капризов SSH). На VPS мост слушает наружу:
```bash
sed -i 's/listen_ip = 127.0.0.1/listen_ip = 0.0.0.0/' /opt/TelegramOnly/ha_stack/rns/config
ufw allow 50061/tcp
systemctl restart ha-reticulum-bridge
```
Клиентский `C:\Project\client_rns\config`:
```
[reticulum]
  enable_transport = No
  share_instance = No
[interfaces]
  [[TCP Client Interface]]
    type = TCPClientInterface
    interface_enabled = yes
    target_host = 138.226.221.219     # публичный IP VPS
    target_port = 50061
```
> ⚠️ 50061 открыт наружу. Трафик Reticulum шифрован, gRPC-стаб остаётся на
> localhost VPS. После тестов вернуть `listen_ip=127.0.0.1` + `ufw delete allow
> 50061/tcp`. Для боевого режима — режим B или I2P (этап 3).

### Режим B — через SSH-туннель (безопасный)
`target_host = 127.0.0.1` в клиентском конфиге, и туннель с **локальной машины**:
```powershell
ssh -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes \
    -L 127.0.0.1:50061:127.0.0.1:50061 -L 127.0.0.1:50051:127.0.0.1:50055 root@<VPS_IP>
```
Грабли, на которые наступили:
- **`-N`** — без удалённой оболочки; иначе сессия (а с ней проброс) может сразу
  закрыться по логин-скрипту хостера.
- **`127.0.0.1:` перед портом** — иначе Windows OpenSSH биндит проброс на IPv6
  `[::1]`, а RNS ходит на IPv4 `127.0.0.1` → `WinError 10061`.
- **`ServerAliveInterval`** — против разрыва «простаивающего» соединения.
- Проверка: `Test-NetConnection 127.0.0.1 -Port 50061` → `TcpTestSucceeded : True`.
- На некоторых хостерах (наш — Eurohoster) туннель всё равно флапал — тогда режим A
  или I2P.

### Режим C — I2P через нативные туннели i2pd (путь 2, этап 3)
Боевой анонимный путь, публичный порт наружу **не нужен**. ⚠️ НЕ используем RNS
`I2PInterface` (через SAM) — он не работает (см. [RETICULUM_VPS.md](RETICULUM_VPS.md)
§12.5). Вместо этого i2pd сам несёт I2P, а RNS ходит обычным TCP на localhost:

```
RNS ↔ TCP ↔ i2pd client-туннель ↔ I2P ↔ i2pd server-туннель ↔ TCP ↔ мост
```

**На VPS** — server-туннель i2pd заворачивает `TCPServerInterface 127.0.0.1:50061`
в стабильный I2P-destination (`/etc/i2pd/tunnels.d/ha-bridge.conf`, ключи
`ha-bridge.dat`). b32 моста:
```bash
curl -s "http://127.0.0.1:7070/?page=i2p_tunnels" | sed 's/<[^>]*>/ /g' | grep -i ha-bridge
#   -> ha-bridge ⇒ x4utehodm3nezw5xb72nrdzhx3jestb2yqjdnbn46ljgzqd53aza.b32.i2p:50061
```

**На клиенте** — i2pd + client-туннель (SAM не нужен):
```bash
# macOS:
brew install i2pd && brew services start i2pd
# в $(brew --prefix)/etc/i2pd/tunnels.conf дописать:
#   [ha-bridge-client]
#   type = client
#   address = 127.0.0.1
#   port = 50061
#   destination = x4utehodm3nezw5xb72nrdzhx3jestb2yqjdnbn46ljgzqd53aza.b32.i2p
#   destinationport = 50061
#   keys = ha-bridge-client.dat
brew services restart i2pd        # поднимется local listener 127.0.0.1:50061
```
Клиентский RNS-конфиг указывает на **localhost** (i2pd сделает I2P сам):
```
[interfaces]
  [[TCP Client Interface]]
    type = TCPClientInterface
    interface_enabled = yes
    target_host = 127.0.0.1
    target_port = 50061
```
> `--bridge-hash` тот же (`12bbf2cd…`, транспортно-независим). Меняется только то,
> на какой `target_host` смотрит RNS: публичный IP (режим A) или localhost-туннель
> i2pd (режим C). Первый коннект по I2P медленный (туннели строятся, leaseset
> резолвится 1–5 мин). Команды теста — те же, что в §2.

## 2. Запуск клиента и тестовые команды

```powershell
cd C:\Project\ProjectPython\UDP_gRPC_COM_Lite
.\.venv\Scripts\python.exe gui_app/run_all_servers.py --mode cli
```
В приглашении `cli_SHSK-M>` (всё одной строкой; путь — через `/`, не `\`):

| Тест | Команда | Ожидаемый ответ |
|---|---|---|
| Датчик T/H (proto) | `device send --device mi_th_sensor --block BU --cmd read --protocol reticulum --bridge-hash <HASH> --rns-config C:/Project/client_rns` | `mi_th_sensor: T=23.5C H=45%` |
| Лампочка (proto, WRITE) | `device send --device mi_bulb --block BU --cmd write --led on --protocol reticulum --bridge-hash <HASH> --rns-config C:/Project/client_rns` | `mi_bulb: power=on, brightness=80` |
| Сырой UDP (`/udp_raw`) | `send --hex "01 00" --protocol reticulum --bridge-hash <HASH> --rns-config C:/Project/client_rns` | `mi_bulb raw ok` |

**Стрим событий (этап 2)** — отдельным демо-скриптом (не в CLI), из корня
`UDP_gRPC_COM_Lite`:
```powershell
.\.venv\Scripts\python.exe -m reticulum_transport.subscribe_demo `
  --bridge-hash <HASH> --rns-config C:/Project/client_rns --block BU --max 5
```
Ожидание: 5 строк `event: mi_th_sensor type=EVENT_UNKNOWN ... payload='T=23.xC H=45%'`,
затем `received 5 events`. (Стрим идёт по `RNS.Channel` на открытом Link.)

> **macOS-вариант команд** (пути и интерпретатор отличаются от Windows): из корня
> `~/Project/ProjectPython/UDP_gRPC_COM_Lite`, интерпретатор `.venv/bin/python3`,
> конфиги — `~/Project/client_rns` (режим A) и `~/Project/client_rns_i2p` (режим C).
> ⚠️ В свежем venv поставь зависимости: `.venv/bin/pip install rns lxmf` (в
> `requirements.txt` не закреплены). Пример (режим C, I2P):
> ```bash
> .venv/bin/python3 -m reticulum_transport.subscribe_demo \
>   --bridge-hash 12bbf2cd888546cf78bc76112e0b3bbe --rns-config ~/Project/client_rns_i2p --block BU --max 5
> ```

> ✅ Проверено в проде 2026-06-26, hash `12bbf2cd888546cf78bc76112e0b3bbe`:
> - **Режим A (TCP)**: мост `0.0.0.0:50061` + `iptables`, публичный IP
>   `138.226.221.219` — 5 событий `mi_th_sensor` (`T=23.5→23.9C H=45%`).
> - **Режим C (I2P, путь 2)**: client-туннель i2pd → b32 `x4utehodm…b32.i2p`,
>   RNS на `127.0.0.1:50061` — стрим зелёный (Mac). Первый коннект медленный.

## 3. Важные грабли (чек-лист при ошибке)

- **`Could not recognize device`** — старый код; нужен фикс CLI (device_id
  проходит как есть на reticulum-пути). Уже в `UDP_gRPC_COM_Lite`.
- **`Could not load config file, creating default...` + multicast-варнинги** —
  путь к конфигу побит бэкслешами (`C:\...` → `C:...`). Используй прямые слеши:
  `--rns-config C:/Project/client_rns`.
- **`WinError 10061` / `no path to bridge`** — нет связи до 50061: проверь режим
  (A: `ufw`+`0.0.0.0`+IP клиента; B: туннель жив, IPv4-бинд, `Test-NetConnection`;
  C: i2pd слушает `127.0.0.1:50061`, см. ниже).
- **Режим C, `no path to bridge` сразу после рестарта i2pd** — на VPS пересоздался
  leaseset моста, клиент держит истёкший (в логе i2pd `Lease is expired already` /
  `Streaming: Resend … another remote lease`). Это переходное: подожди 1–5 мин
  (республиш + резолв leaseset на молодом роутере) и повтори — у нас зазеленело с
  3-й попытки. Проверка готовности i2pd на клиенте:
  `curl -s http://127.0.0.1:7070/?page=i2p_tunnels | grep -i ha-bridge`.
- **Режим C, локальный listener не поднят** — `lsof -nP -iTCP:50061 -sTCP:LISTEN`
  должен показать `i2pd`. Нет → проверь блок `[ha-bridge-client]` в `tunnels.conf`
  и `brew services restart i2pd`. SAM на клиенте для пути 2 **не нужен**.
- **Singleton:** `RNS.Reticulum` — один на процесс. **Одна reticulum-команда на
  сессию CLI.** Для следующей — выйди и запусти CLI заново.
- **Сравнение с TCP gRPC напрямую:** `--protocol grpc` шлёт на `localhost:50051`
  по блоку (BU=50051) — для стаба пробрось `-L 127.0.0.1:50051:127.0.0.1:50055`.

## 4. Что доказывает успешный тест

`device send --protocol reticulum` → RNS Link → мост (VPS) → локальный gRPC
`DeviceControlService` (стаб Mi-Home) → `CommandResponse` → обратно по Reticulum.
То есть прото `CommandRequest→CommandResponse` ходит по стеку Reticulum на
удалённый сервер. Статус и нюансы — в [RETICULUM_TRANSPORT.md](RETICULUM_TRANSPORT.md) §7.
