# ApiRgRPC — Reticulum (RNS/LXMF) desktop client

Цензуроустойчивый клиент на **Reticulum Network Stack**, построенный по образцу
[`ApiNgRPC`](../ApiNgRPC): **Tauri (Rust) каркас + внешний движок**. Только вместо
`sing-box` движок здесь — **`rns-engine`** (Python `rns` + `lxmf`), которым
Rust-сторона управляет через line-delimited JSON по stdin/stdout.

> Полный учебник по самому Reticulum (что это, по ОС, сценарии, API) — см.
> [`Reticulum.md`](Reticulum.md).

## Что это и чего НЕ это
- ✅ зашифрованный обмен сообщениями/данными поверх RNS/LXMF, без DNS/IP и без
  центральной инфраструктуры; работает поверх TCP / I2P / LoRa.
- ❌ это **не** VPN/прокси для сёрфинга clearnet (для этого — `ApiNgRPC`/VLESS).

## Архитектура
```
tauri-app/                 # десктоп-клиент (Tauri v2)
  src/                     # фронтенд (vanilla JS + Tauri global API, без бандлера)
  src-tauri/
    src/lib.rs             # bootstrap, состояние, регистрация команд
    src/engine.rs          # запуск/IPC sidecar-движка (как менеджер sing-box)
    src/commands.rs        # Tauri-команды: start/stop/status/announce/send/...
rns-engine/                # Python-движок RNS+LXMF (sidecar)
  rns_engine.py            # JSON-протокол по stdin/stdout
  requirements.txt
```
Поток: `Frontend (JS) → Tauri commands (Rust) → engine.rs → rns-engine (Python) → Reticulum`.
События из сети идут обратно: `rns-engine (stdout JSON) → engine.rs → Tauri event "rns-event" → Frontend`.

## Что взято лучшее из ApiNgRPC
- модель «UI + внешний движок-процесс» с управлением через команды/IPC;
- хранение данных в app-data каталоге ОС;
- чистая остановка движка при закрытии окна;
- минимальный фронтенд без тяжёлого фреймворка.

## Предпосылки
- Rust (stable) + Tauri v2 системные зависимости (WebView2 на Windows).
- Node.js (для `@tauri-apps/cli`).
- Python 3.9+ с `rns` и `lxmf` (для dev-режима движок запускается как скрипт).

## Запуск (dev)
```bash
# 1) движок — зависимости
cd rns-engine && python -m pip install -r requirements.txt && cd ..

# 2) клиент
cd tauri-app
npm install
npm run tauri dev
```
В dev-режиме `engine.rs` сам запустит `python ../rns-engine/rns_engine.py`
(fallback), создаст identity и app-data, и нажатие «Запустить» поднимет Reticulum.

Проверка движка отдельно (без UI):
```bash
cd rns-engine
python rns_engine.py --store ./store --config ./.reticulum --name Test
# в stdin можно слать: {"cmd":"address"}  {"cmd":"announce"}  {"cmd":"status"}
```

## Сборка релиза
```bash
# 1) собрать движок в один бинарь (PyInstaller)
cd rns-engine && bash build_engine.sh   # → dist/rns-engine(.exe)

# 2) положить бинарь в ресурсы Tauri и включить в bundle
#    cp rns-engine/dist/rns-engine* tauri-app/src-tauri/  (или в binaries/)
#    в tauri.conf.json → "bundle.resources": ["rns-engine*"]

# 3) собрать приложение
cd ../tauri-app && npm run tauri build
```
`engine.rs` в релизе сначала ищет бандленный `rns-engine(.exe)` в resource-каталоге,
и только при отсутствии падает на dev-fallback (`python`).

## Статус
`v0.1.0` — рабочий каркас: запуск движка, identity/адрес, анонс, приём/отправка
LXMF-сообщений, список пиров, журнал. Дальше — профили/несколько интерфейсов
(TCP/I2P/RNode), история, шифрование локального стора, PIN (как в ApiNgRPC).

## TODO (ближайшее)
- [ ] PyInstaller-сборка движка + бандлинг ресурса + `bundle.resources`.
- [ ] Иконки (`npm run tauri icon`) — нужны для `tauri build`.
- [ ] Экран интерфейсов: TCP к VPS / I2P / RNode (запись `~/.reticulum/config`).
- [ ] Хранение профилей и истории в app-data, PIN-замок (портировать из ApiNgRPC).
- [ ] Доставка PROPAGATED (через propagation-узлы) для оффлайн-адресатов.
