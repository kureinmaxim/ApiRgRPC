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

## Связанный проект

- `C:\Project\ProjectPython\UDP_gRPC_COM_Lite` — серверная/прокси-сторона
  (Python, gRPC-стрим, контракт `device_control.proto`, адаптер Home Assistant).
  Изменения для Reticulum-транспорта там — **только в CLI** (переключатель
  протокола + `ReticulumTransport`); подробности — в `RETICULUM_TRANSPORT.md`.

## Структура

- `tauri-app/` — десктоп-оболочка (Rust `src-tauri/` + фронтенд).
- `rns-engine/` — Python-движок Reticulum (`rns_engine.py`), зависимости в
  `requirements.txt`. Сюда же ляжет RNS-мост (`rns-engine/bridge/`, этап 1).
