# BUILD — сборка ApiRgRPC (macOS и Windows)

ApiRgRPC = **Tauri-оболочка** (`tauri-app/`, Rust + web-фронт) + **Python
RNS-движок** (`rns-engine/`, sidecar). Сборка релиза — два шага:

1. **Движок** → один self-contained бинарь (`rns-engine` / `rns-engine.exe`) через
   PyInstaller.
2. **Tauri** бандлит этот бинарь как resource и собирает приложение (`.app`/`.dmg`
   на macOS, `.msi`/`.exe` на Windows).

В **dev**-режиме движок собирать не нужно: `engine.rs` сам запускает
`python3 ../rns-engine/rns_engine.py` (fallback). Бандл нужен только для релиза.

---

## 0. Предварительные требования

| Инструмент | macOS | Windows |
|---|---|---|
| Rust (stable) | `brew install rustup` → `rustup-init` | `rustup` с rust-lang.org |
| Node.js (LTS) | `brew install node` | installer с nodejs.org |
| Python 3.9+ | `brew install python` | python.org (+ «Add to PATH») |
| WebView | встроен | **WebView2 Runtime** (обычно уже есть; иначе — Evergreen с сайта MS) |
| Сборка C | Xcode Command Line Tools (`xcode-select --install`) | «Desktop development with C++» (Visual Studio Build Tools) |

Tauri CLI ставится локально проектом (`npm install` в `tauri-app/` подтянет
`@tauri-apps/cli`); глобально не обязателен.

---

## 1. Dev-запуск (без сборки бинарей)

```bash
# 1) зависимости движка (вкл. rns, lxmf, protobuf для device-control)
cd rns-engine
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
cd ..

# 2) фронт + Tauri dev
cd tauri-app
npm install
npm run tauri dev
```

`engine.rs` поднимет `python3 ../rns-engine/rns_engine.py` сам. В окне: задай
интерфейс (TCP/I2P) → «Запустить» → получишь RNS-адрес, пиров, сообщения и панель
device-control.

> ⚠️ **Важно:** dev-режим использует Python из `PATH` (`python3`/`python`). Чтобы
> были доступны `rns`/`lxmf`/`protobuf`, активируй venv движка **в том же
> терминале**, из которого запускаешь `npm run tauri dev` (или поставь зависимости
> в системный Python).

Терминальный клиент без Tauri — `rns-engine/rns_cli.py` (см. [README](README.md)).

---

## 2. Сборка движка в один бинарь (для релиза)

```bash
cd rns-engine
bash build_engine.sh
# → dist/rns-engine        (macOS/Linux)
# → dist/rns-engine.exe    (Windows, запускать build_engine.sh из Git Bash, либо
#   повторить команду PyInstaller вручную в PowerShell)
```

Скрипт делает `pyinstaller --onefile` с `--collect-all RNS --collect-all LXMF`
(RNS грузит интерфейсы динамически — без этого frozen-бинарь падает на
`_synthesize_interface`) и `--hidden-import` для `device_control` / `proto` /
`bridge` (device-control к HA-мосту).

**Положить бинарь в ресурсы Tauri:**

```bash
cp dist/rns-engine* ../tauri-app/src-tauri/
```

В `tauri-app/src-tauri/tauri.conf.json` бандл движка уже прописан:

```json
"bundle": {
  "category": "Utility",
  "resources": ["rns-engine*"]
}
```

Поэтому достаточно положить бинарь в `src-tauri/` (шаг выше) — отдельно
править конфиг не нужно. В релизе `engine.rs` сначала ищет `rns-engine(.exe)` в
resource-каталоге и только при отсутствии падает на dev-fallback `python`.

> ⚠️ Раз `resources` указывает на `rns-engine*`, **`tauri build` упадёт, если
> бинарь не собран/не скопирован** в `src-tauri/` — поэтому сначала §2, потом
> сборка. (`tauri dev` ресурсы не бандлит, поэтому работает и без бинаря —
> движок берётся через python-fallback.)

---

## 3. macOS — `.app` / `.dmg`

```bash
cd rns-engine && bash build_engine.sh && cp dist/rns-engine ../tauri-app/src-tauri/ && cd ..
# resources/category в tauri.conf.json уже настроены — править не нужно

cd tauri-app
npm install
npm run tauri build
```

Итог:
```
tauri-app/src-tauri/target/release/bundle/macos/ApiRgRPC.app
tauri-app/src-tauri/target/release/bundle/dmg/ApiRgRPC_0.1.0_<arch>.dmg
```

- **Universal (Intel + Apple Silicon):** `npm run tauri build -- --target universal-apple-darwin`
  (нужны оба rust-таргета: `rustup target add x86_64-apple-darwin aarch64-apple-darwin`).
- **Подпись/нотаризация** (для раздачи без предупреждений Gatekeeper): задать
  `APPLE_SIGNING_IDENTITY` (+ `APPLE_ID`/`APPLE_PASSWORD`/`APPLE_TEAM_ID` для
  notarize) перед `tauri build`. Без подписи приложение запустится локально, но у
  получателя будет карантин — снять: `xattr -dr com.apple.quarantine ApiRgRPC.app`.

---

## 4. Windows — `.msi` / `.exe`

```powershell
# 1) движок (из Git Bash или вручную PyInstaller в venv)
cd rns-engine
python -m venv .venv ; .venv\Scripts\activate
python -m pip install -r requirements.txt pyinstaller
pyinstaller --onefile --name rns-engine --collect-all RNS --collect-all LXMF `
  --paths . --hidden-import device_control --hidden-import proto.device_control_pb2 `
  --hidden-import bridge.bridge rns_engine.py
copy dist\rns-engine.exe ..\tauri-app\src-tauri\
cd ..

# 2) Tauri (resources: ["rns-engine*"] в tauri.conf.json уже выставлен)
cd tauri-app
npm install
npm run tauri build
```

Итог:
```
tauri-app\src-tauri\target\release\bundle\nsis\ApiRgRPC_0.1.0_x64-setup.exe
tauri-app\src-tauri\target\release\bundle\msi\ApiRgRPC_0.1.0_x64_en-US.msi
```

- Нужен **WebView2 Runtime** на машине пользователя (Tauri может встроить
  установщик WebView2 — см. `bundle.windows.webviewInstallMode` в tauri.conf.json).
- Антивирус/Defender может ругаться на неподписанный PyInstaller-бинарь (как с
  i2pd) — для раздачи подписать (`signtool` / `bundle.windows.certificateThumbprint`).

---

## 5. Куда смотреть при проблемах

- **`Reticulum/LXMF not installed`** при старте движка (dev) — не активирован venv
  движка / нет `rns lxmf` в текущем Python. Поставь зависимости (§1).
- **`NameError: name 'Interface' is not defined`** в собранном бинаре — RNS не
  подхватился PyInstaller'ом. Проверь, что в команде есть `--collect-all RNS`
  (и `--collect-all LXMF`).
- **device-control не работает в релизе** (`No module named 'proto'/'bridge'`) —
  проверь `--hidden-import device_control / proto.device_control_pb2 / bridge.bridge`
  в `build_engine.sh`.
- **движок не находится в релизе** — бинарь не скопирован в `src-tauri/` или
  `bundle.resources` пуст. `engine.rs` ищет `rns-engine(.exe)` в resource-каталоге.
- **нет связи (пиры/мост не видны)** — не задан интерфейс. В окне «Интерфейсы
  (RNS)» укажи TCP host:port (и/или I2P) → «Применить и перезапустить». Конфиг
  пишется в `<app data>/reticulum/config`.

---

## 6. Где что лежит

| | macOS | Windows |
|---|---|---|
| Конфиг RNS приложения | `~/Library/Application Support/com.apirg.reticulum/reticulum/config` | `%APPDATA%\com.apirg.reticulum\reticulum\config` |
| Хранилище движка (identity, LXMF) | `…/com.apirg.reticulum/store` | `%APPDATA%\…\store` |
| Артефакты сборки | `tauri-app/src-tauri/target/release/bundle/` | то же |

---

*Связанные доки: [README.md](README.md) (обзор, dev, CLI), [Reticulum.md](Reticulum.md)
(учебник по RNS), [RETICULUM_TESTING.md](RETICULUM_TESTING.md) и
[CLI_RETICULUM.md](CLI_RETICULUM.md) (тест транспорта и команды).*
