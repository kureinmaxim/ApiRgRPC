# RETICULUM_TESTING.md — как тестировать Reticulum-транспорт (этап 1)

Рабочая процедура e2e-теста: клиент `UDP_gRPC_COM_Lite` (Windows) ↔ HA-стек на
VPS через **Reticulum**. Зафиксировано по факту успешного прогона 2026-06-23
(`mi_th_sensor: T=23.5C H=45%`).

## 0. Что должно быть готово

**На VPS** — HA-стек установлен (`scripts/install_ha_stack.sh`, см. TelegramOnly
`DEPLOY.md §6.7`). Проверка на VPS:
```bash
systemctl is-active ha-reticulum-bridge ha-stub-grpc ha-stub-udp   # три active
ss -tlnp | grep 50061                                              # мост слушает
journalctl -u ha-reticulum-bridge -n 5 --no-pager | grep destination
#   -> bridge up, destination = <BRIDGE_HASH>   (стабилен между рестартами)
```
Запомни `<BRIDGE_HASH>` (напр. `d46bed01f4654bda8d07b6c97a030af9`).

**На клиенте** — RNS-конфиг `C:\Project\client_rns\config` (см. §1).

## 1. Два режима связи клиент↔мост

### Режим A — прямое подключение (рабочий, для теста)
Самый надёжный для проверки (без капризов SSH). На VPS мост слушает наружу:
```bash
sed -i 's/listen_ip = 127.0.0.1/listen_ip = 0.0.0.0/' /opt/ha-test/ha_stack/rns/config
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
