# RETICULUM_TESTING.md — как тестировать Reticulum-транспорт (этап 1)

Рабочая процедура e2e-теста: клиент `UDP_gRPC_COM_Lite` (Windows) ↔ HA-стек на
VPS через **Reticulum**. Зафиксировано по факту успешного прогона 2026-06-23
(`mi_th_sensor: T=23.5C H=45%`).

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

## 1. Два режима связи клиент↔мост

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

## 3. Важные грабли (чек-лист при ошибке)

- **`Could not recognize device`** — старый код; нужен фикс CLI (device_id
  проходит как есть на reticulum-пути). Уже в `UDP_gRPC_COM_Lite`.
- **`Could not load config file, creating default...` + multicast-варнинги** —
  путь к конфигу побит бэкслешами (`C:\...` → `C:...`). Используй прямые слеши:
  `--rns-config C:/Project/client_rns`.
- **`WinError 10061` / `no path to bridge`** — нет связи до 50061: проверь режим
  (A: `ufw`+`0.0.0.0`+IP клиента; B: туннель жив, IPv4-бинд, `Test-NetConnection`).
- **Singleton:** `RNS.Reticulum` — один на процесс. **Одна reticulum-команда на
  сессию CLI.** Для следующей — выйди и запусти CLI заново.
- **Сравнение с TCP gRPC напрямую:** `--protocol grpc` шлёт на `localhost:50051`
  по блоку (BU=50051) — для стаба пробрось `-L 127.0.0.1:50051:127.0.0.1:50055`.

## 4. Что доказывает успешный тест

`device send --protocol reticulum` → RNS Link → мост (VPS) → локальный gRPC
`DeviceControlService` (стаб Mi-Home) → `CommandResponse` → обратно по Reticulum.
То есть прото `CommandRequest→CommandResponse` ходит по стеку Reticulum на
удалённый сервер. Статус и нюансы — в [RETICULUM_TRANSPORT.md](RETICULUM_TRANSPORT.md) §7.
