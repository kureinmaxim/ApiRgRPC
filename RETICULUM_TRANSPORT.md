# RETICULUM_TRANSPORT.md — второй транспорт (Reticulum/I2P) для HA-сервера

Живой документ: **цели, дизайн, этапы и текущий статус** работы по добавлению
второго транспорта — доставки прото-сообщений `device_control.proto` поверх
стека **Reticulum** (на первом этапе по простому интерфейсу, затем через
**I2P**) — в дополнение к уже работающему TCP/IP-gRPC.

Статус документа: **дизайн утверждён, реализация не начата.**
Дата: 2026-06-22.

---

## 1. Цель и рамки

**Цель (зачем):** эксперимент и задел на будущее — отработать паттерн
«прото поверх Reticulum» в реальном сценарии, не ломая существующий рабочий
TCP/IP-транспорт.

**Только для кастомного HA-сервера.** Серверы BU/BZ/BF и существующий gRPC/TCP
путь **не трогаем**.

**Минимальная цель PoC (этап 1):** *connectivity + один round-trip* — отправитель
посылает HA-серверу **одно** сообщение `device_control.proto` через Reticulum и
получает прото-ответ. Доказали, что прото ходит по новому стеку.

**Задел (этап 2, позже):** превратить открытый `RNS.Link` в двусторонний
**стрим** (аналог текущего gRPC-стрима).

**Не входит в PoC (YAGNI):** GUI-кнопки, ретраи/очереди, шифрование сверх того,
что даёт Reticulum, переезд BU/BZ/BF, замена существующего транспорта.

---

## 2. Топология и компоненты

```
[UDP_gRPC_COM_Lite CLI]                         [VPS]
  send (protocol=reticulum)                ┌─────────────────────────────┐
        │                                  │  RNS-мост (ApiRgRPC)         │
        ▼                                  │   RNS.Destination IN/SINGLE  │
  ReticulumTransport ── RNS.Link.request ──┼─► register_request_handler   │
   "/device_control" (proto bytes)         │     │ decode proto          │
        ▲                                  │     ▼ локальный gRPC         │
        └──────── response (proto bytes) ──┼── UDP_gRPC_COM_Lite / HA     │
                                           └─────────────────────────────┘
   (транспорт: сейчас TCPInterface, позже I2PInterface — код не меняется)
```

### A. Контракт «по проводу» (общий)
- Источник истины — `device_control.proto` (в UDP_gRPC_COM_Lite). Для моста и
  клиента он вендорится/генерируется в ApiRgRPC.
- Соглашения Reticulum (как реализовано):
  - app_name = `apirgrpc`, aspects = `("bridge", "devicecontrol")`
    (по ним строится Destination Hash моста, тип IN/SINGLE);
  - **два пути запроса** на одном Destination:
    - `"/device_control"` — тело = сериализованный `CommandRequest`, ответ =
      `CommandResponse` (для команды `device send`, прото → локальный gRPC);
    - `"/udp_raw"` — тело = **сырые байты** UDP-пакета, ответ = сырой UDP-ответ
      (для верхнеуровневого `send`; мост форвардит байты UDP-ом на прокси).

**Порты (PoC, localhost):**
- HA-сервер gRPC `DeviceControlService` — **`127.0.0.1:50055`** (это `--grpc` моста).
- RNS `TCPServerInterface` моста (listen) — **`127.0.0.1:50061`**; клиент
  подключается `TCPClientInterface target_port = 50061`.
- Оба порта вне зарезервированного Windows-диапазона `50508–50607`.

### B. RNS-мост (приёмник) — **в ApiRgRPC**, `rns-engine/bridge/`
Отдельный headless-процесс на Python, запускается на VPS рядом с HA.
- Поднимает `RNS.Destination` (IN, SINGLE), `register_request_handler("/device_control", …)`.
- Принял bytes → декодировал прото → **локальный gRPC** к UDP_gRPC_COM_Lite
  (существующий путь/HA-адаптер `home_automation/adapters/home_assistant.py`) →
  получил ответ → сериализовал прото → вернул как response линка.
- Использует пакет `rns` (тот же, что в `rns-engine/requirements.txt`).
- **Параллелен** существующему LXMF-пути в `rns-engine/rns_engine.py` (тот —
  для человеческого мессенджинга; этот — для RPC device-control). LXMF не трогаем.

### C. Клиент-транспорт (отправитель) — **в UDP_gRPC_COM_Lite**, только CLI
- Переключатель протокола в CLI: `protocol tcp|reticulum` (или флаг `--protocol`).
- Новый self-contained модуль `ReticulumTransport` (пакет `rns`):
  открывает `RNS.Link` к Destination Hash моста, вызывает
  `link.request("/device_control", proto_bytes, response_callback=…)`, ждёт ответ.
- Существующий `send` **переиспользуется** — он лишь отдаёт прото в выбранный
  транспорт. Никаких других изменений в UDP_gRPC_COM_Lite.
- (Позже тот же паттерн отправителя переиспользуется в GUI-клиенте ApiRgRPC.)

---

## 3. Поток данных (этап 1, простой интерфейс)

1. CLI: `protocol reticulum`, затем существующая команда `send …`.
2. `ReticulumTransport`: при необходимости `request_path` к хэшу моста, ждёт путь,
   устанавливает `RNS.Link`, шлёт `link.request("/device_control", proto)`.
3. RNS поверх `TCPClientInterface` → `TCPServerInterface` моста.
4. Мост: handler декодирует прото → локальный gRPC к UDP_gRPC_COM_Lite/HA →
   ответный прото → возвращает как response.
5. Клиент: `response_callback` печатает ответ в CLI.

---

## 4. Этапность транспорта (ключевое)

- **Этап 1 — простой интерфейс:** в конфиге RNS — `TCPServerInterface` (мост, VPS)
  и `TCPClientInterface` (отправитель). Прямой Reticulum-линк, **без I2P**.
  Цель — доказать round-trip и мост.
- **Этап 3 — I2P:** заменяем **только** секцию интерфейса в конфиге RNS на
  `I2PInterface` (требует `i2pd` с включённым SAM API на обоих концах). **Код
  приложения не меняется** — Reticulum абстрагирует среду. I2P — это «смена
  одёжки», а не переписывание.

> Раздел описывает только **интерфейс** (среду). Стрим (этап 2) от интерфейса
> не зависит и работает поверх того же транспорта — поэтому здесь между этапами
> 1 и 3 он не упомянут. Полная нумерация этапов — в разделе 7.

---

## 5. Обработка ошибок

- Таймаут установки `Link` / нет пути к мосту → клиент сообщает ошибку, можно
  повторить или вернуться на `protocol tcp`. Не падаем.
- Ошибка локального gRPC в мосте → возвращаем прото-ответ с кодом ошибки.
- Битый прото / неизвестный путь запроса → reject с понятной ошибкой.
- Неверный Destination Hash моста → лог + сообщение; хэш моста клиент берёт из
  конфига (out-of-band, как и принято в Reticulum).

---

## 6. Тестирование

- **Локальный loopback (до VPS/I2P):** мост + отправитель на одной машине через
  `TCPInterface` на `localhost`; гоняем известный `device_control`-запрос,
  проверяем прото-ответ (pytest в духе `UDP_gRPC_COM_Lite/test4all/`). Снимает
  риск ещё до выезда на VPS и до I2P.
- После loopback — повтор на VPS (этап 1), затем — переключение на I2P (этап 3).

---

## 7. Этапы и статус (чек-лист)

Легенда: ⬜ не начато · 🟦 в работе · ✅ готово

### Этап 0 — дизайн
- ✅ Согласованы цель, топология, подход (RNS Link + request/response)
- ✅ Этот документ создан и закоммичен

### Этап 1 — PoC round-trip по простому интерфейсу (`TCPInterface`)
- ✅ Вендоринг/генерация `device_control` прото-стабов в ApiRgRPC (для моста)
- ✅ RNS-мост `rns-engine/bridge/` — Destination + `register_request_handler`
- ✅ Мост → локальный gRPC к UDP_gRPC_COM_Lite/HA → прото-ответ (`GrpcCommandBackend`)
- ✅ Точка входа моста `rns-engine/bridge/run_bridge.py`
- ✅ `ReticulumTransport.send_command` в UDP_gRPC_COM_Lite (`reticulum_transport/`)
- ✅ Переключатель `--protocol grpc|udp|reticulum` в команде `device send` (Task 4c)
- ✅ Локальный loopback-тест round-trip (мост в subprocess + клиент), зелёный ×3
- ✅ **Второй путь `/udp_raw`** для верхнеуровневого `send` (сырой UDP): raw-обработчик
  в мосте (форвард байтов UDP-ом на прокси, Task 4d-A) + `ReticulumTransport.send_raw`
  + `--protocol udp|reticulum` в верхнеуровневом `send` (Task 4d-B); loopback и
  routing-тесты зелёные
- ✅ **Прогон на боевом VPS (Task 5):** `device send --protocol reticulum`
  (`mi_th_sensor`) вернул `T=23.5C H=45%` через Reticulum на удалённый VPS
  (мост `--grpc 127.0.0.1:50055`, RNS listen 50061). Прото-round-trip доказан в
  проде 2026-06-23.
  - Нюанс: SSH-туннель к VPS (Eurohoster) **флапал** (соединение рвётся, даже с
    `ssh -N -o ServerAliveInterval`), давая `WinError 10061`. Для теста временно
    открыли `listen_ip=0.0.0.0` + `ufw allow 50061` и ходили **напрямую** на
    публичный IP. Трафик Reticulum шифрован, gRPC-стаб остался на localhost.
    Для боевого режима — вернуть `127.0.0.1` + туннель (или перейти на I2P, этап 3,
    где публичный порт вообще не нужен).
  - 2026-06-25: хэш моста изменился (`12bbf2cd888546cf78bc76112e0b3bbe`) —
    вероятно, при переустановке `ha_stack` было пересоздано RNS-identity.
    На VPS отсутствует `ufw` (firewall через `iptables`); мост снова на `127.0.0.1`.
    Для режима A: `iptables -I INPUT -p tcp --dport 50061 -j ACCEPT` вместо `ufw`.
  - 2026-06-25: **повторный прогон зелёный** — `mi_th_sensor: T=23.5C H=45%`
    через `listen_ip=0.0.0.0` + `iptables` (режим A, прямой IP).

### Инфраструктура
- ✅ Отслеживание версии приложения «как в ApiNgRPC»: `scripts/version.py`
  (status/check/sync/bump/set) синхронизирует версию по `tauri-app/*` +
  `VERSION_MANAGEMENT.md` (Task INFRA-1)

**Реализационные заметки (RNS 1.3.5):**
- `RNS.Reticulum` — процессный синглтон; линк к destination *своего же* процесса
  не поднимается. Поэтому loopback-тесты гоняют мост в **отдельном процессе**
  (TCPServerInterface), а клиент — в тест-процессе (TCPClientInterface). Это
  ближе к боевой топологии, чем одно-процессный вариант.
- Каждому интерфейсу в конфиге RNS нужен `interface_enabled = yes`, иначе RNS
  его пропускает (поднимает 0 интерфейсов).
- Прото-стабы в UDP_gRPC_COM_Lite лежат в `shared/device_control_pb2.py`
  (на `sys.path` добавляется `shared/`).
- Request/response-API RNS 1.3.5 совпал с заложенным в плане без адаптации.

### Этап 2 — стрим ✅
- ✅ Стрим `DeviceEvent` поверх `RNS.Channel` на открытом Link
  (`SubscribeMessage`/`DeviceEventMessage`); мост форвардит gRPC `SubscribeEvents`
- ✅ Стаб `SubscribeEvents` (5 периодических событий), `GrpcCommandBackend.subscribe_events`
- ✅ Клиент `ReticulumTransport.subscribe_events` + `subscribe_demo.py`
- ✅ Loopback-тесты зелёные (мост: `test_event_stream.py`; клиент: `test_reticulum_subscribe.py`)
- ✅ **Прогон стрима на боевом VPS (2026-06-26):** `subscribe_demo --block BU --max 5`
  вернул 5 событий `mi_th_sensor` (`T=23.5→23.9C H=45%`) по `RNS.Channel` поверх
  Link на удалённый VPS, затем `received 5 events`. Стрим `DeviceEvent` доказан в
  проде. Режим A (мост `listen_ip=0.0.0.0` + `iptables --dport 50061`, прямой
  публичный IP `138.226.221.219`); dest hash `12bbf2cd888546cf78bc76112e0b3bbe`,
  стаб `SubscribeEvents` на `127.0.0.1:50055`.

### Этап 3 — I2P (позже)
- ⬜ `i2pd` + SAM на VPS и локально
- ⬜ Замена секции интерфейса RNS на `I2PInterface` (код не меняется)
- ⬜ Round-trip и стрим зелёные поверх I2P

### Этап 4 — продуктовый клиент
- ⬜ Перенос паттерна отправителя в GUI-клиент ApiRgRPC (Win/macOS)

---

## 8. Затронутые проекты

| Проект | Что меняется |
|---|---|
| **ApiRgRPC** | новый RNS-мост `rns-engine/bridge/`; вендоринг прото; этот документ; (этап 4) GUI-клиент |
| **UDP_gRPC_COM_Lite** | **только CLI**: переключатель протокола + `ReticulumTransport`; существующий `send` переиспользуется |
| BU/BZ/BF, существующий gRPC/TCP | **не трогаем** |

---

## 9. Этап 2 — стрим (дизайн, к реализации)

**Цель:** двусторонний/серверный поток событий поверх Reticulum — зеркало gRPC
`SubscribeEvents(EventSubscribeRequest) returns (stream DeviceEvent)`.

**Примитив RNS:** держать открытый `RNS.Link` и гонять по нему поток через
**`RNS.Channel` + `RNS.Buffer`** (в RNS 1.x — надёжный байтовый канал поверх
Link). Либо слать по Link length-prefixed сериализованные `DeviceEvent`.

**Компоненты:**
- **Стаб** `stub_server.py`: реализовать `SubscribeEvents` — периодически (раз в
  N сек) отдавать `DeviceEvent` (напр. показания `mi_th_sensor`), для теста.
- **Мост** (`bridge/`): на запрос подписки открыть `RNS.Link`, поднять
  `Channel/Buffer`, локально вызвать gRPC `SubscribeEvents` и **форвардить**
  каждый `DeviceEvent` в Buffer клиента. Закрытие Link → закрыть gRPC-стрим.
- **Клиент** (`ReticulumTransport.subscribe_events()`): открыть Link, подписаться,
  читать `DeviceEvent` по мере прихода (callback/generator).

**PoC-критерий:** клиент получает несколько `DeviceEvent` подряд по Reticulum.
**Реализовывать** отдельным циклом brainstorm → writing-plans → код (это фича, не
конфиг). Транспорт (TCP/I2P) на стрим не влияет.

## 10. Этап 3 — I2P (процедура, код не меняется)

Снимает боль с SSH-туннелем (публичный порт не нужен). Нужен **i2pd с SAM API**
на ОБОИХ концах.

**1. i2pd + SAM:**
- VPS: `apt install -y i2pd`; в `/etc/i2pd/i2pd.conf` секция `[sam] enabled = true`
  (порт 7656); `systemctl enable --now i2pd`.
- Клиент (Windows): установить i2pd, включить SAM (7656).

**2. RNS-конфиг — заменить TCP-интерфейс на I2P:**
- Мост (`ha_stack/rns/config`):
  ```
  [[I2P]]
    type = I2PInterface
    interface_enabled = yes
  ```
  RNS при старте логирует **I2P b32-адрес** моста — забрать из
  `journalctl -u ha-reticulum-bridge`.
- Клиент (`client_rns/config`):
  ```
  [[I2P]]
    type = I2PInterface
    interface_enabled = yes
    peers = <bridge_i2p_b32>
  ```

**3.** Перезапустить мост и клиента. `--bridge-hash` тот же (RNS-identity не
меняется). Первый коннект медленный (I2P строит туннели 30–120 c). Публичный порт
закрыть (`listen_ip` назад на 127.0.0.1 не нужен — I2P не слушает TCP наружу).

> Команды/режимы теста — в [RETICULUM_TESTING.md](RETICULUM_TESTING.md).

---

*Документ ведётся по ходу работы: при смене статуса этапа обновляйте чек-лист
в разделе 7.*
