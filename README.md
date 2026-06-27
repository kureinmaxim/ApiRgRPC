<div align="center">

# 🕸️ ApiRgRPC

**Цензуроустойчивый десктоп‑клиент для [Reticulum](https://reticulum.network) (RNS / LXMF).**

Tauri‑каркас на Rust + сменный движок `rns-engine` (Python `rns` + `lxmf`),
управляемый как внешний процесс — по образцу того, как [`ApiNgRPC`](../ApiNgRPC)
управляет `sing-box`.

![version](https://img.shields.io/badge/version-0.1.0-blue)
![tauri](https://img.shields.io/badge/Tauri-v2-24c8db)
![rust](https://img.shields.io/badge/Rust-stable-orange)
![reticulum](https://img.shields.io/badge/Reticulum-RNS%2FLXMF-7d5fff)
![status](https://img.shields.io/badge/status-v0%20skeleton-yellow)

</div>

---

## Что это

ApiRgRPC — это клиент **сети Reticulum**: зашифрованный обмен сообщениями и
данными **без DNS, без IP‑адресов и без центральной инфраструктуры**, поверх чего
угодно — TCP, I2P, LoRa‑радио. Адресация — по криптографическим хэшам личностей.

| ✅ Для чего он | ❌ Чем он НЕ является |
|---|---|
| Устойчивая к цензуре связь (сообщения, файлы, команды) | Это **не** VPN/прокси для сёрфинга clearnet |
| Работа поверх TCP / **I2P** / **LoRa** | Не «выход в интернет через VPS» (для этого — `ApiNgRPC`/VLESS) |
| Сквозное шифрование и forward secrecy по умолчанию | Не требует и не использует общий «сервер» |

> 📚 Полный учебник по самому Reticulum (теория, установка по ОС, сценарии, API) —
> в [`Reticulum.md`](Reticulum.md).

---

## Возможности (v0.1.0)

- 🔑 Стабильная криптоличность (Ed25519/X25519), адрес переживает перезапуск.
- 📡 Анонс себя в сети и автообнаружение пиров (LXMF announces).
- ✉️ Приём и отправка LXMF‑сообщений (с подтверждением доставки).
- 🧭 Живой журнал событий и статус интерфейсов/транспорта.
- 🖥 **Терминальный CLI** (`rns_cli.py`): мессенджер (LXMF) + device-control к HA‑мосту, без Tauri.
- 🧩 Движок изолирован как **сменный sidecar** — позже переписывается на Rust без смены UI.

Дорожная карта — в конце файла.

---

## Архитектура

```
┌─────────────────────────────┐   Tauri events "rns-event"   ┌──────────────────────────┐
│  Frontend (vanilla JS)      │ ◀──────────────────────────── │                          │
│  index.html · main.js       │                               │                          │
│  window.__TAURI__           │ ──────────────────────────▶   │   Rust backend (Tauri)   │
└─────────────────────────────┘   invoke(commands)            │   lib.rs · commands.rs   │
                                                               │   engine.rs (sidecar mgr)│
                                                               └────────────┬─────────────┘
                                                  line‑delimited JSON        │ stdin/stdout
                                                  (как управление sing-box)  ▼
                                                               ┌──────────────────────────┐
                                                               │  rns-engine (Python)     │
                                                               │  RNS + LXMF              │
                                                               └────────────┬─────────────┘
                                                                            ▼
                                                          Reticulum: TCP · I2P · RNode(LoRa)
```

**Поток данных:** `UI → Tauri command (Rust) → engine.rs → rns-engine (Python) → Reticulum`,
а сетевые события идут обратно: `rns-engine (stdout JSON) → engine.rs → Tauri event → UI`.

### Протокол движка (stdin/stdout JSON)
| Команда (→ движку) | Событие (← от движка) |
|---|---|
| `{"cmd":"address"}` | `{"event":"ready","address":"<hex>"}` |
| `{"cmd":"announce"}` | `{"event":"announce","hash":"<hex>","name":"…"}` |
| `{"cmd":"status"}` | `{"event":"status","transport":…,"interfaces":[…]}` |
| `{"cmd":"send","peer":"<hex>","text":"…"}` | `{"event":"rx","from":"<hex>","text":"…"}` |
| `{"cmd":"set_name","name":"…"}` | `{"event":"sent","peer":"<hex>","state":"delivered"}` |

---

## Технологии

| Слой | Стек |
|---|---|
| UI | HTML/CSS + vanilla JS, Tauri global API (без бандлера) |
| Каркас | **Tauri v2**, Rust (stable) |
| Движок | **Python** `rns` + `lxmf` (sidecar, упаковывается PyInstaller) |
| Сеть | Reticulum Network Stack (RNS), LXMF |

---

## Быстрый старт (dev)

Нужно: Rust (+WebView2 на Windows), Node.js, Python 3.9+.

```bash
# 1) зависимости движка
cd rns-engine
python -m pip install -r requirements.txt
cd ..

# 2) клиент
cd tauri-app
npm install
npm run tauri dev
```

В dev‑режиме `engine.rs` сам запустит `python ../rns-engine/rns_engine.py`
(fallback), создаст identity и app‑data. Нажми **«Запустить»** → получишь свой
RNS‑адрес, сможешь анонсировать себя, видеть пиров и слать сообщения.

### Терминальный CLI (без Tauri)

Человеческий REPL поверх движка — два режима в одном: **мессенджер (LXMF)** и
**device-control к HA-мосту** (по RNS, тот же контракт, что у `bridge/`).

```bash
cd rns-engine
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python rns_cli.py --store ./store --name Alice [--config <rns_cfg>] [--bridge-hash <hex>]
```

```text
rns> help                         # список команд
rns> address                      # свой RNS-адрес
rns> announce                     # анонсировать себя
rns> peers                        # обнаруженные пиры
rns> send <peer_hex> привет       # LXMF-сообщение (входящие печатаются сами: 📨)
rns> dev hash <bridge_hex>        # задать HA-мост
rns> dev ping                     # round-trip (READ mi_th_sensor) + latency
rns> dev read mi_th_sensor        # proto READ
rns> dev write mi_bulb on         # proto WRITE
rns> dev stream 5                 # поток DeviceEvent
```

Сырой движок (JSON-протокол для Tauri/отладки протокола):
```bash
cd rns-engine
python rns_engine.py --store ./store --name Test
# затем в stdin:  {"cmd":"address"}   {"cmd":"announce"}   {"cmd":"status"}
```

---

## Сборка релиза

```bash
# 1) движок → один бинарь
cd rns-engine && bash build_engine.sh            # → dist/rns-engine(.exe)

# 2) положить бинарь в ресурсы Tauri:
cp rns-engine/dist/rns-engine* tauri-app/src-tauri/
#    и включить в tauri.conf.json:  "bundle": { "resources": ["rns-engine*"] }

# 3) собрать приложение
cd tauri-app && npm run tauri build
```
В релизе `engine.rs` сначала ищет бандленный `rns-engine(.exe)` в resource‑каталоге,
и лишь при отсутствии падает на dev‑fallback (`python`).

---

## Структура проекта

```
ApiRgRPC/
├── Reticulum.md              # учебник по Reticulum (теория + API)
├── README.md
├── rns-engine/               # Python‑движок (sidecar)
│   ├── rns_engine.py         #   RNS+LXMF, JSON по stdin/stdout (для Tauri)
│   ├── rns_cli.py            #   терминальный CLI: мессенджер + device-control
│   ├── bridge/               #   device-control мост (вендорится на VPS)
│   ├── proto/                #   device_control proto-стабы
│   ├── requirements.txt
│   └── build_engine.sh       #   PyInstaller → один бинарь
└── tauri-app/
    ├── src/                  # фронтенд
    │   ├── index.html · styles.css · main.js
    └── src-tauri/
        ├── src/lib.rs        # bootstrap, состояние, команды
        ├── src/engine.rs     # запуск/IPC sidecar‑движка
        ├── src/commands.rs   # Tauri‑команды
        ├── Cargo.toml · build.rs · tauri.conf.json
        ├── capabilities/default.json
        └── icons/
```

---

## Безопасность

- Весь трафик **E2E‑шифрован** (Reticulum: X25519/Ed25519/AES‑256/HMAC, forward secrecy).
- Приватный ключ (`identity`) — это «ты»; он **не коммитится** (`.gitignore`) и
  хранится в app‑data. Не публикуй его.
- Голый TCP‑интерфейс виден провайдеру как факт соединения (но не содержимое);
  чтобы скрыть и сам факт — используй **I2P** или радио.

---

## Связь с ApiNgRPC

ApiRgRPC намеренно повторяет проверенную архитектуру `ApiNgRPC` («UI + внешний
движок‑процесс»), но решает другую задачу: не обход DPI ради clearnet, а
**устойчивый скрытый канал связи**. Их можно использовать вместе: управляющий
канал (уведомления/команды) — на Reticulum, пользовательский сёрфинг — на VLESS.

---

## Дорожная карта

- [ ] PyInstaller‑бандлинг движка + `bundle.resources`.
- [ ] Экран интерфейсов: TCP к VPS / **I2P** / **RNode (LoRa)** (запись `~/.reticulum/config`).
- [ ] Профили, история сообщений, шифрование локального стора, **PIN‑замок** (портировать из ApiNgRPC).
- [ ] `PROPAGATED`‑доставка (оффлайн‑адресаты через propagation‑узлы).
- [ ] Передача файлов (RNS Resource), статусы доставки в UI.
- [ ] Опционально: нативный Rust‑движок вместо Python (когда стабилизируется).

---

## Лицензия и благодарности

- Reticulum / LXMF — © Mark Qvist, https://reticulum.network
- ApiRgRPC — © kureinmaxim

## Ссылки
- Reticulum: https://github.com/markqvist/Reticulum · [Manual](https://markqvist.github.io/Reticulum/manual/)
- LXMF: https://github.com/markqvist/LXMF
- Sideband (референс‑клиент): https://github.com/markqvist/Sideband
