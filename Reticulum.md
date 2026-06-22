# Reticulum.md — учебное руководство: что это, как запустить и как написать свой клиент

Полное, структурированное руководство по **Reticulum Network Stack (RNS)**: что
это, чем он принципиально отличается от твоего VLESS/Reality‑VPN, как поставить и
настроить под Linux / macOS / Windows / Android / встраиваемые устройства, и как
написать **свой клиент** по образцу `ApiNgRPC` (Tauri + движок), но под Reticulum.

> Автор стека — Mark Qvist. Сайт: https://reticulum.network · Код:
> https://github.com/markqvist/Reticulum · Docs: https://markqvist.github.io/Reticulum/manual/

---

## 0. ГЛАВНОЕ СНАЧАЛА: Reticulum ≠ VPN/прокси

Чтобы не путать с тем, что ты уже делал (VLESS‑Reality, Hysteria — «выход в
интернет через VPS, обход DPI»):

| | Твой ApiNgRPC (VLESS/Reality) | Reticulum (RNS) |
|---|---|---|
| Цель | вывести **весь интернет‑трафик** через VPS, замаскировав под TLS | построить **свою зашифрованную сеть** для сообщений/данных/команд |
| Адресация | IP/домены, выход в clearnet | **криптографические адреса** (хэши), без DNS и IP |
| Что даёт | доступ к заблокированным сайтам | устойчивые к цензуре **комм‑каналы**, меш, off‑grid |
| Среда | TCP/UDP поверх интернета | поверх **чего угодно**: TCP, UDP, I2P, LoRa‑радио, serial, packet‑radio |
| Маскировка от DPI | да (Reality мимикрирует под сайт) | **нет встроенной** TLS‑маскировки; но есть транспорт через I2P/радио, который DPI не видит |
| Инфраструктура | нужен VPS‑exit | **не нужна** центральная инфраструктура вовсе |

**Вывод:** Reticulum **не заменит** твой VLESS для «открыть YouTube через VPS».
Он решает другую задачу — **зашифрованная связь и передача данных, которую крайне
трудно заблокировать или вывести из строя** (мессенджер, передача файлов,
удалённые команды, телеметрия, меш‑сети). Для анти‑DPI он интересен тем, что может
работать поверх **I2P** или **радио (LoRa)** — каналов, которые провайдерский DPI
в принципе не контролирует.

---

## 1. Что такое Reticulum (суть)

**Reticulum — это сетевой стек** (как TCP/IP, но другой), а не приложение. Он даёт
приложениям сеть со следующими свойствами:

- **Сквозное шифрование по умолчанию.** Любой трафик зашифрован; нешифрованного
  режима для обычных приёмников нет.
- **Никакой центральной инфраструктуры.** Нет DNS, нет регистраторов, нет
  «сервера». Узлы находят друг друга сами.
- **Адреса = криптография.** Конечная точка (Destination) адресуется
  **усечённым хэшем** её публичного ключа (16 байт). Знать адрес = достаточно,
  чтобы зашифровать ей сообщение, которое прочитает только она.
- **Самонастраиваемая многоскачковая маршрутизация.** Узлы с ролью **Transport**
  ретранслируют и строят маршруты автоматически (через «анонсы»).
- **Анонимность инициатора.** Можно установить связь, не раскрывая, кто ты.
- **Работает на тонких каналах.** Спроектирован вплоть до ~5 бит/с (LoRa), MTU
  пакета мал (≈500 байт), большие данные передаются «ресурсами» с чанками.
- **Forward secrecy.** Сессии (**Link**) используют эфемерные ключи (ECDH‑ратчет).

Эталонная реализация — на **Python** (пакет `rns`). Есть зрелые приложения
поверх: **Sideband** (GUI‑мессенджер, в т.ч. Android), **Nomad Network**
(терминальный «меш‑интернет»/BBS), **MeshChat** (веб‑UI), а также формат
сообщений **LXMF** (как «почта» поверх RNS).

---

## 2. Архитектура и ключевые понятия

```
[ Твоё приложение ]                 ← Sideband / Nomad / твой клиент
        │
[ LXMF ]  (опц. слой сообщений: "почта" поверх RNS, оффлайн‑доставка)
        │
[ RNS API ]  Identity · Destination · Link · Packet · Resource · Announce
        │
[ Transport ]  маршрутизация, путь к адресату, ретрансляция
        │
[ Interfaces ]  TCP · UDP · Auto(Ethernet) · RNode(LoRa) · Serial · KISS · I2P · Pipe
        │
[ Любая физическая среда ]
```

Понятия:
- **Identity** — пара ключей (Ed25519 для подписи + X25519 для обмена). Это «кто ты».
- **Destination** — именованная конечная точка у Identity. Типы:
  - `SINGLE` — приватная адресуемая точка (большинство случаев),
  - `GROUP` — симметрично‑шифрованная группа,
  - `PLAIN` — без шифрования (редко, для служебного),
  - `LINK` — устанавливается динамически.
  Адрес = хэш от `app_name` + `aspects` + публичного ключа.
- **Announce** — широковещательное «я существую, вот мой адрес/ключ», расходится
  по transport‑узлам; так другие узнают путь и публичный ключ.
- **Link** — зашифрованная сессия между двумя Destination с forward secrecy
  (как «TLS‑сессия», но в терминах RNS).
- **Packet** — единица передачи (мал, ~383 байта полезной нагрузки).
- **Resource** — механизм передачи больших объёмов (файлы) с разбиением и
  компрессией поверх Link.
- **Transport node** — узел с `enable_transport = Yes`: маршрутизирует чужой
  трафик. На VPS обычно поднимают именно его как «точку сбора» меша.

---

## 3. Криптография (коротко и точно)

- Обмен ключами: **X25519 (ECDH)**.
- Подписи: **Ed25519**.
- Симметрика: **AES‑256‑CBC** + **HMAC‑SHA256** (токен‑формат), ключи через **HKDF**.
- Хэш: **SHA‑256** (адреса — усечение до 128 бит).
- **Forward secrecy** на Link за счёт эфемерных X25519‑ключей.
- Метаданные минимальны: транзитный узел видит только следующий хоп, не «кто‑с‑кем».

---

## 4. Установка по операционным системам

Базовый пакет один и тот же — `rns` (Python 3.7+). Приложения ставятся отдельно.

### 4.1 Linux (Debian/Ubuntu, в т.ч. твои VPS)
```bash
sudo apt update && sudo apt install -y python3-pip
pip3 install rns                      # ядро + утилиты (rnsd, rnstatus, ...)
pip3 install lxmf nomadnet            # мессенджер-слой + терминальное приложение
rnsd                                  # запустить демон (создаст ~/.reticulum/config)
```
systemd‑сервис для VPS (transport‑узел):
```ini
# /etc/systemd/system/rnsd.service
[Unit]
Description=Reticulum Network Stack Daemon
After=network.target
[Service]
ExecStart=/usr/local/bin/rnsd
User=root
Restart=on-failure
[Install]
WantedBy=multi-user.target
```
```bash
systemctl enable --now rnsd
```

### 4.2 macOS
```bash
brew install python      # если нет
pip3 install rns lxmf nomadnet
rnsd
# GUI-мессенджер Sideband: см. релизы https://github.com/markqvist/Sideband
```

### 4.3 Windows
```powershell
# Python 3.x с python.org (отметь "Add to PATH")
pip install rns
pip install lxmf nomadnet
rnsd            # демон; конфиг в %USERPROFILE%\.reticulum\config
# Sideband для Windows — готовый .exe в релизах Sideband
```

### 4.4 Android
- Проще всего — приложение **Sideband** (мессенджер на RNS/LXMF): F‑Droid или APK
  из релизов. Не требует root, умеет TCP/I2P/RNode (LoRa по USB/BLE).
- Для разработки/CLI — **Termux** → `pkg install python` → `pip install rns`.

### 4.5 Raspberry Pi / встраиваемые / off‑grid
- `pip install rns` на Raspberry Pi OS — как на Linux.
- **RNode** (LoRa‑радио на базе ESP32/LilyGO) — «железный интерфейс» Reticulum для
  связи без интернета на километры. Прошивка/настройка: `rnodeconf`.
- Reticulum штатно идёт по UART/serial/KISS — подходит для микроконтроллеров и
  пакетного радио.

---

## 5. Конфигурация и интерфейсы

Конфиг: `~/.reticulum/config` (Windows: `%USERPROFILE%\.reticulum\config`).
Создаётся автоматически при первом `rnsd`. Формат — секции `[[…]]`.

### 5.1 Клиент, подключающийся к твоему VPS по TCP
```ini
[reticulum]
  enable_transport = No
  share_instance = Yes

[interfaces]
  [[Default Interface]]
    type = AutoInterface        # авто-обнаружение в локалке (Ethernet/Wi-Fi)
    enabled = yes

  [[My VPS]]
    type = TCPClientInterface
    enabled = yes
    target_host = 138.124.71.73
    target_port = 4242
```

### 5.2 VPS как transport‑узел (точка сбора меша)
```ini
[reticulum]
  enable_transport = Yes        # ВАЖНО: маршрутизирует чужой трафик
  share_instance = Yes

[interfaces]
  [[TCP Server]]
    type = TCPServerInterface
    enabled = yes
    listen_ip = 0.0.0.0
    listen_port = 4242
```
(открой порт: `ufw allow 4242/tcp`)

### 5.3 Скрытый канал поверх I2P (интересно против DPI)
```ini
  [[I2P]]
    type = I2PInterface
    enabled = yes
    connectable = yes
```
I2P‑транспорт прячет сам факт соединения от провайдера (DPI не видит «к кому» и
«что» — в отличие от голого TCP).

### 5.4 Радио‑интерфейс (off‑grid, LoRa)
```ini
  [[RNode LoRa]]
    type = RNodeInterface
    enabled = yes
    port = /dev/ttyUSB0
    frequency = 867200000
    bandwidth = 125000
    spreadingfactor = 8
    codingrate = 5
    txpower = 7
```

### 5.5 Прочие интерфейсы
`UDPInterface`, `SerialInterface`, `KISSInterface`, `AX25KISSInterface`,
`PipeInterface` — комбинируются: один узел может одновременно быть в TCP, в I2P и
на радио, «сшивая» сети.

---

## 6. Утилиты из коробки

| Команда | Что делает |
|---|---|
| `rnsd` | демон стека (держит интерфейсы, маршрутизацию) |
| `rnstatus` | статус интерфейсов, трафик, известные пути |
| `rnpath <hash>` | показать/запросить маршрут к адресу |
| `rnprobe <app> <aspects> <hash>` | пинг‑проба достижимости Destination |
| `rncp` | копирование файлов между узлами (через Resource) |
| `rnx` | удалённое выполнение команд (как ssh поверх RNS) |
| `rnid` | работа с Identity (создать/показать) |
| `rnodeconf` | прошивка/настройка RNode (LoRa) |

---

## 7. Готовые приложения (чтобы попробовать сразу)

- **Sideband** — GUI‑мессенджер (desktop + Android): сообщения, голос, передача
  файлов, карта, телеметрия. Лучшее «поиграться без кода».
- **Nomad Network** — терминальный «меш‑интернет»: страницы, доски, ЛС, поверх RNS.
- **MeshChat** — веб‑интерфейс к LXMF (удобно для desktop).
- **LXMF** — не приложение, а формат/роутер сообщений (оффлайн‑доставка, как
  «почта»). На нём строят мессенджеры.

---

## 8. Сценарии применения

1. **Цензуроустойчивый мессенджер**: твои устройства + VPS‑transport. Сообщения
   E2E‑шифрованы, доставка переживает блокировки (особенно через I2P‑интерфейс).
2. **Off‑grid связь**: два RNode (LoRa) на километры без интернета и сотовой связи.
3. **Удалённое управление/телеметрия**: `rnx`/свой клиент — команды и данные с
   устройств в поле через любой доступный канал.
4. **Передача файлов** между узлами без облака (`rncp`/Resource).
5. **Мост сетей**: один узел сшивает интернет‑сегмент (TCP/I2P) и радио‑сегмент.
6. **Связь поверх твоего VPS 71.73**: даже если MTS душит VLESS‑Reality, RNS‑канал
   через TCP или I2P к VPS даёт независимый зашифрованный контур для сообщений/команд.

---

## 9. Пишем своего клиента: Python RNS API

Это «hello world» уровня сети — два скрипта.

### 9.1 Приёмник (анонсирует адрес и принимает сообщения)
```python
import RNS

APP = "mychat"
ASPECT = "messenger"

reticulum = RNS.Reticulum()                 # читает ~/.reticulum/config
identity  = RNS.Identity()                  # или RNS.Identity.from_file("id")

dest = RNS.Destination(
    identity, RNS.Destination.IN, RNS.Destination.SINGLE, APP, ASPECT
)

def on_packet(data, packet):
    print("RX:", data.decode("utf-8", "replace"))

dest.set_packet_callback(on_packet)
dest.announce()                              # «я существую», расходится по transport
print("My address:", RNS.prettyhexrep(dest.hash))
input("Listening... Enter to quit\n")
```

### 9.2 Отправитель (по известному адресу)
```python
import RNS, time

APP, ASPECT = "mychat", "messenger"
dest_hash = bytes.fromhex("PASTE_RECIPIENT_HASH_HERE")

reticulum = RNS.Reticulum()

if not RNS.Transport.has_path(dest_hash):
    RNS.Transport.request_path(dest_hash)    # узнать маршрут/ключ
    while not RNS.Transport.has_path(dest_hash):
        time.sleep(0.1)

recipient_identity = RNS.Identity.recall(dest_hash)
dest = RNS.Destination(
    recipient_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, APP, ASPECT
)
RNS.Packet(dest, "Привет из RNS".encode("utf-8")).send()
```

### 9.3 Сессия с forward secrecy (Link) и большие данные (Resource)
```python
link = RNS.Link(dest)                        # установить зашифрованную сессию
link.set_link_established_callback(lambda l: RNS.Resource("bigfile.bin", l))
```

### 9.4 Мессенджер на LXMF (оффлайн‑доставка, рекомендуемый слой)
```python
import RNS, LXMF

router = LXMF.LXMRouter(storagepath="./lxmf-store")
my_id  = RNS.Identity()
local  = router.register_delivery_identity(my_id, display_name="Me")
router.announce(local.hash)

# отправка:
peer = bytes.fromhex("PEER_LXMF_HASH")
RNS.Transport.request_path(peer)
recipient = RNS.Destination(RNS.Identity.recall(peer), RNS.Destination.OUT,
                            RNS.Destination.SINGLE, "lxmf", "delivery")
msg = LXMF.LXMessage(recipient, local, "Текст", title="Тема")
router.handle_outbound(msg)                  # доставит, когда адресат появится
```

---

## 10. «Как мой проект, но новый»: архитектура клиента под Reticulum

Твой `ApiNgRPC` = **Tauri (Rust) UI + внешний движок** (`sing-box.exe`/`naive.exe`),
которым UI управляет через команды и temp‑конфиги. Под Reticulum повторяем тот же
паттерн — это самый быстрый и надёжный путь, потому что зрелый стек — на Python.

### Вариант A (рекомендую) — Tauri UI + RNS как sidecar‑движок
```
[ Tauri (Rust) GUI ]  ← как сейчас в ApiNgRPC
        │  локальный IPC (stdin/stdout JSON, или TCP 127.0.0.1, или файл-команды)
[ rns-engine (Python) ]  обёртка над RNS + LXMF (PyInstaller → один .exe)
        │
[ Reticulum: TCP / I2P / RNode ]
```
- **UI/бэкенд на Rust/Tauri** переиспользуешь почти как есть (профили,
  PIN, диагностика, упаковка инсталлятора).
- **Движок** — маленький Python‑сервис `rns_engine.py` (RNS + LXMF), собранный
  `PyInstaller`‑ом в `rns-engine.exe`, который ты бандлишь в инсталлятор (как
  `sing-box.exe`). Он экспонирует мини‑API: `announce`, `send`, `recv`, `peers`,
  `status` — например, простым JSON‑протоколом по `127.0.0.1:PORT`.
- Tauri‑команды (`commands/...`) дергают этот локальный API ровно как сейчас
  дёргают gRPC/процессы. Профили из «server/uuid/sni» превращаются в «interface
  (TCP/I2P/RNode) + identity + peers».

Скелет движка:
```python
# rns_engine.py  → PyInstaller: pyinstaller --onefile rns_engine.py
import RNS, LXMF, json, socketserver

class Engine:
    def __init__(self):
        self.r = RNS.Reticulum()
        self.id = RNS.Identity()
        self.router = LXMF.LXMRouter(storagepath="./store")
        self.local = self.router.register_delivery_identity(self.id, display_name="ApiNg-RNS")
        self.router.register_delivery_callback(self._on_msg)
    def _on_msg(self, m): print(json.dumps({"event":"rx","from":RNS.hexrep(m.source_hash),"text":m.content.decode()}), flush=True)
    def send(self, peer_hex, text):
        peer = bytes.fromhex(peer_hex); RNS.Transport.request_path(peer)
        rcpt = RNS.Destination(RNS.Identity.recall(peer), RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf","delivery")
        self.router.handle_outbound(LXMF.LXMessage(rcpt, self.local, text))
    def address(self): return RNS.hexrep(self.local.hash)
# + тонкий цикл чтения команд из stdin (JSON) и вызов методов
```

### Вариант B — нативно на Rust
Есть community‑реализации Reticulum на Rust (ищи `reticulum` / `reticulum-rs` на
crates.io/GitHub), но они **частичны и не дотягивают** до эталонного Python‑RNS по
совместимости и фичам (LXMF, все интерфейсы, transport). Для прод‑клиента сейчас
рискованно; годится для экспериментов/embedded. Если хочешь «всё на Rust» — закладывай
время на доработку и тесты совместимости с реальной RNS‑сетью.

### Вариант C — поверх готового
Не писать сеть вообще, а взять **Sideband/Nomad/MeshChat** как референс или даже
форкнуть UI, а себе оставить только свою обвязку. Быстро, но меньше «свой проект».

**Рекомендация:** начни с **Варианта A** — переиспользуешь весь свой Tauri‑каркас,
а сетевую сложность отдаёшь зрелому Python‑RNS. Когда стабилизируется — при желании
постепенно перепишешь движок на Rust (Вариант B) без смены UI.

---

## 11. Безопасность и приватность

- Всё E2E‑шифровано; приватный ключ (`Identity`) — это «ты», храни его как секрет
  (на диске в `~/.reticulum/` или в своём защищённом сторе, как PIN в ApiNgRPC).
- Транзитные transport‑узлы видят только следующий хоп, не содержимое и не
  «кто‑с‑кем».
- Голый TCP‑интерфейс **виден провайдеру как факт соединения** (но не содержимое).
  Хочешь скрыть сам факт — используй **I2P‑интерфейс** или радио.
- Это не «анонимайзер для clearnet»: для выхода в обычный интернет он не предназначен.

---

## 12. Применимость к твоей анти‑DPI задаче

- **Не замена VLESS** для «сёрфинг clearnet через VPS». Это другой инструмент.
- **Где полезен прямо сейчас:** независимый, цензуроустойчивый контур связи между
  твоими устройствами и VPS (сообщения, команды, файлы), который трудно
  заблокировать — особенно через **I2P** (DPF/DPI не видит) или **LoRa** (вне
  интернета вообще).
- **Идея гибрида:** управляющий канал (уведомления/команды боту, выдача ключей)
  держать на Reticulum/LXMF — он переживёт блокировки, когда VLESS «качает», — а
  пользовательский сёрфинг оставить на VLESS/Hysteria.

---

## 13. Ресурсы

- Manual: https://markqvist.github.io/Reticulum/manual/
- Reticulum (RNS): https://github.com/markqvist/Reticulum
- LXMF (сообщения): https://github.com/markqvist/LXMF
- Sideband (GUI/Android): https://github.com/markqvist/Sideband
- Nomad Network (TUI): https://github.com/markqvist/NomadNet
- MeshChat (web UI): https://github.com/liamcottle/reticulum-meshchat
- RNode (LoRa железо): https://unsigned.io/rnode/
- Сообщество: матрица/форумы по ссылкам с reticulum.network

> Резюме: Reticulum — это «свой интернет» с шифрованием по умолчанию и без
> инфраструктуры. Для обхода DPI ради clearnet — оставайся на VLESS. Для
> устойчивой скрытой связи/меша и «нового проекта‑клиента» — бери RNS, начни с
> Python‑движка под Tauri‑каркас ApiNgRPC (Вариант A).
