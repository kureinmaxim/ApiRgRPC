# CLI_RETICULUM.md — команды управления Reticulum-транспортом

Сводка всех команд, которыми гоняется и обслуживается Reticulum-транспорт
ApiRgRPC ↔ HA-стек на VPS. Две стороны:

- **Серверные команды** (на VPS) — статус/перезапуск моста и I2P: через
  Telegram-бота `TelegramOnly` **и** через серверный SSH-CLI (`admin_cli` /
  `cli_dashboard`). Дают `bridge hash` и `b32`, которые нужны клиенту.
- **Клиентские команды** (на ПК) — собственно тест/обмен из CLI
  `UDP_gRPC_COM_Lite` (`device send --protocol reticulum`, `subscribe_demo`).

Связанные доки: [RETICULUM_TESTING.md](RETICULUM_TESTING.md) (как тестировать,
режимы A/B/C), [RETICULUM_VPS.md](RETICULUM_VPS.md) §12 (серверная карта, I2P
путь 2), [RETICULUM_TRANSPORT.md](RETICULUM_TRANSPORT.md) (дизайн/этапы).

---

## 1. Серверные команды (VPS)

Одни и те же команды доступны двумя путями (обе вызывают общий
`reticulum_manager.py`, поэтому вывод одинаковый):

- **Telegram-бот** `TelegramOnly` — отправить команду боту (только админ).
- **SSH-CLI на сервере** — `admin_cli` / интерактивный `cli_dashboard`
  (раздел «🛰 Reticulum / HA-стек»). Удобно, когда бот недоступен.

| Команда | Что делает | Опасная? |
|---|---|---|
| `/reticulum_status` | Статус 3 сервисов HA-стека (`ha-reticulum-bridge`, `ha-stub-grpc`, `ha-stub-udp`), слушает ли мост `:50061`, **bridge hash**, и блок I2P: `i2pd` + **b32** (если установлен) | нет (read-only) |
| `/reticulum_hash` | Только **bridge destination hash** (для `--bridge-hash` у клиента). Транспортно-независим | нет |
| `/reticulum_i2p` | I2P-путь (путь 2): статус `i2pd` + **b32** серверного туннеля `ha-bridge` (для клиентского i2pd-туннеля) | нет |
| `/reticulum_restart` | Перезапуск **трёх** сервисов HA-стека. i2pd **не трогает** (рестарт i2pd роняет leaseset на минуты) | да (рестарт) |

> i2pd перезапускается отдельно и осознанно (`systemctl restart i2pd`) — после
> него клиентам нужно 1–5 мин на ре-резолв leaseset (см. RETICULUM_TESTING.md §3).

### Пример вывода `/reticulum_status`
```
🛰 Reticulum / HA-стек

🟢 ha-reticulum-bridge
🟢 ha-stub-grpc
🟢 ha-stub-udp
Мост слушает :50061 — да

Bridge hash: 12bbf2cd888546cf78bc76112e0b3bbe

🟢 i2pd (I2P, путь 2)
I2P b32: x4utehodm3nezw5xb72nrdzhx3jestb2yqjdnbn46ljgzqd53aza.b32.i2p

Управление: /reticulum_restart, /reticulum_hash, /reticulum_i2p
```

### Эквиваленты «руками» на VPS (если CLI/бот недоступны)
```bash
systemctl is-active ha-reticulum-bridge ha-stub-grpc ha-stub-udp i2pd   # статусы
journalctl -u ha-reticulum-bridge -n 50 --no-pager | grep destination   # bridge hash
curl -s "http://127.0.0.1:7070/?page=i2p_tunnels" | sed 's/<[^>]*>/ /g' | grep -i ha-bridge   # b32
systemctl restart ha-reticulum-bridge ha-stub-grpc ha-stub-udp          # рестарт HA-стека
```

---

## 2. Клиентские команды (ПК, CLI `UDP_gRPC_COM_Lite`)

Берёшь `<HASH>` из `/reticulum_hash` и (для I2P) `<b32>` из `/reticulum_i2p`,
подставляешь в команды клиента. `--rns-config` — каталог с RNS-конфигом
(см. режимы A/B/C в [RETICULUM_TESTING.md](RETICULUM_TESTING.md) §1).

```bash
# round-trip: датчик (proto READ) через Reticulum
device send --device mi_th_sensor --block BU --cmd read \
  --protocol reticulum --bridge-hash <HASH> --rns-config <client_rns_dir>
#   -> mi_th_sensor: T=23.5C H=45%

# round-trip: лампочка (proto WRITE)
device send --device mi_bulb --block BU --cmd write --led on \
  --protocol reticulum --bridge-hash <HASH> --rns-config <client_rns_dir>
#   -> mi_bulb: power=on, brightness=80

# сырой UDP-путь (/udp_raw) через Reticulum
send --hex "01 00" --protocol reticulum --bridge-hash <HASH> --rns-config <client_rns_dir>
#   -> mi_bulb raw ok

# стрим событий (этап 2) — отдельным демо-скриптом, не в CLI
python -m reticulum_transport.subscribe_demo \
  --bridge-hash <HASH> --rns-config <client_rns_dir> --block BU --max 5
#   -> 5× event: mi_th_sensor ... ; received 5 events
```

> `<HASH>` (напр. `12bbf2cd888546cf78bc76112e0b3bbe`) **один и тот же** для всех
> транспортов — он транспортно-независим. Меняется только RNS-конфиг
> (`--rns-config`): прямой TCP / SSH-туннель / I2P-туннель i2pd. Подробности и
> macOS-варианты команд — [RETICULUM_TESTING.md](RETICULUM_TESTING.md) §2.
> Полный перечень клиентских CLI-флагов — `CLI_COMMANDS_GUIDE.md` в
> `UDP_gRPC_COM_Lite` (раздел «Reticulum-транспорт»).

---

## 3. Типовой сценарий

1. На VPS (бот/CLI): `/reticulum_status` → убедиться, что всё 🟢, забрать
   `bridge hash` (и `b32`, если идём по I2P).
2. На клиенте: выбрать режим связи (A прямой TCP / B SSH-туннель / C I2P) и
   собрать `<client_rns_dir>/config` — см. [RETICULUM_TESTING.md](RETICULUM_TESTING.md) §1.
3. Прогнать `device send --protocol reticulum …` или `subscribe_demo`.
4. Если связи нет — `/reticulum_status` (мост жив? слушает?), затем чек-лист
   грабель [RETICULUM_TESTING.md](RETICULUM_TESTING.md) §3.

---

*Источник истины по серверным командам — `TelegramOnly`
(`reticulum_manager.py`, `admin_cli.py`, `cli_dashboard.py`); по клиентским —
`UDP_gRPC_COM_Lite` (`reticulum_transport/`, `CLI_COMMANDS_GUIDE.md`).*
