# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## Project Overview

**ApiRgRPC** — клиент Reticulum для Windows/macOS: оболочка на **Tauri**
(`tauri-app/`) + Python **RNS sidecar** (`rns-engine/`, на `rns` + `lxmf`,
общение с хостом по JSON через stdin/stdout). На старте — скелет
Reticulum-клиента (v0.1.0).

## Ключевые документы

- [README.md](README.md) — обзор и запуск проекта.
- [Reticulum.md](Reticulum.md) — праймер по RNS и паттерну клиента.
- [Zen_of_Reticulum_RU.md](Zen_of_Reticulum_RU.md) — философия Reticulum
  (русская адаптация «Zen of Reticulum» Марка Квиста, для новичка).
- **[RETICULUM_TRANSPORT.md](RETICULUM_TRANSPORT.md) — план, дизайн, этапы и
  текущий статус работы по второму транспорту (Reticulum/I2P) для HA-сервера.**
  Живой документ: при смене статуса этапа обновляйте чек-лист (раздел 7).
- [RETICULUM_TESTING.md](RETICULUM_TESTING.md) — как гонять e2e-тесты сейчас
  (режимы связи A/B/C, команды, грабли). Проверено в проде 2026-06-23.
- [CLI_RETICULUM.md](CLI_RETICULUM.md) — все команды управления транспортом:
  серверные `/reticulum_*` (бот TelegramOnly + SSH-CLI) и клиентские
  (`device send --protocol reticulum`, `subscribe_demo`).
- [RETICULUM_VPS.md](RETICULUM_VPS.md) — **серверная инсталляция**: как развёрнут
  и работает стек на VPS (сервисы, порты, пути, архитектура), клиентский конфиг и
  будущее поведение в exe, следующие шаги. Живой документ.
- [I2P.md](I2P.md) — введение в I2P (история, как работает, перспективы) +
  практическая справка по i2pd. Транспорт этапа 3. Живой документ (раздел 7).
- [VERSION_MANAGEMENT.md](VERSION_MANAGEMENT.md) — схема версионирования и `scripts/version.py` (status/check/sync/bump/set).

## Связанный проект

- `C:\Project\ProjectPython\UDP_gRPC_COM_Lite` — серверная/прокси-сторона
  (Python, gRPC-стрим, контракт `device_control.proto`, адаптер Home Assistant).
  Изменения для Reticulum-транспорта там — **только в CLI** (переключатель
  протокола + `ReticulumTransport`); подробности — в `RETICULUM_TRANSPORT.md`.

## Структура

- `tauri-app/` — десктоп-оболочка (Rust `src-tauri/` + фронтенд).
- `rns-engine/` — Python-движок Reticulum (`rns_engine.py`), зависимости в
  `requirements.txt`. Сюда же ляжет RNS-мост (`rns-engine/bridge/`, этап 1).
