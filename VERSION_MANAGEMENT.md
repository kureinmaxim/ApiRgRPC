# Version Management - ApiRgRPC

Управление версиями для `ApiRgRPC`.

Важно:
- source of truth: `tauri-app/src-tauri/Cargo.toml` (`[package].version`)
- в отличие от родственного проекта `ApiNgRPC`, здесь **нет** `shared-rs/`
  крейта и **нет** `installer/`, поэтому эти цели синхронизации опущены

## Quick Reference

Все команды ниже по умолчанию запускаются **из корня репозитория**:
- `C:\Project\ApiRgRPC`
- не из `tauri-app\`
- не из `scripts\`

### Windows

```powershell
# from C:\Project\ApiRgRPC
python scripts\version.py status
python scripts\version.py check
python scripts\version.py sync
python scripts\version.py bump patch
python scripts\version.py bump minor
python scripts\version.py bump major
python scripts\version.py set 1.0.0
```

### macOS / Linux

```bash
# from /path/to/ApiRgRPC
python3 scripts/version.py status
python3 scripts/version.py check
python3 scripts/version.py sync
python3 scripts/version.py bump patch
python3 scripts/version.py bump minor
python3 scripts/version.py bump major
python3 scripts/version.py set 1.0.0
```

## Source Of Truth

Главный источник версии:

```toml
# tauri-app/src-tauri/Cargo.toml
[package]
version = "X.Y.Z"
```

После изменения версии здесь выполните `sync`, чтобы подтянуть ее в остальные
манифесты.

## Synced Files

| File | Purpose |
|------|---------|
| `tauri-app/src-tauri/Cargo.toml` | canonical version source (Tauri crate) |
| `tauri-app/package.json` | frontend package version |
| `tauri-app/src-tauri/tauri.conf.json` | desktop bundle version |
| `README.md` | Shields badge version (`.../badge/version-X.Y.Z-blue`) |

## Commands

`status` — показать версии во всех файлах и пометить рассинхрон:

```powershell
python scripts\version.py status
```

`check` — то же, что `status`, но возвращает ненулевой код выхода при
рассинхроне (удобно для CI):

```powershell
python scripts\version.py check
```

`sync` — синхронизировать все файлы от `tauri-app/src-tauri/Cargo.toml`
(или к явно указанной версии: `sync 1.2.3`):

```powershell
python scripts\version.py sync
```

`bump` — поднять patch/minor/major:

```powershell
python scripts\version.py bump patch
python scripts\version.py bump minor
python scripts\version.py bump major
```

`set` — установить конкретную версию:

```powershell
python scripts\version.py set 1.0.0
```

## Manual Update Checklist

Если скрипт временно не подходит, проверьте вручную:
- `tauri-app/src-tauri/Cargo.toml` -> `version`
- `tauri-app/package.json` -> `version`
- `tauri-app/src-tauri/tauri.conf.json` -> `version`
- `README.md` -> badge `version-X.Y.Z-blue`

## Notes

- safest path для релиза: сначала `status`/`check`, затем `sync`, затем сборка
- README badge обновляется автоматически через `scripts/version.py`
- если в проекте позже появятся `shared-rs/Cargo.toml` или
  `installer/*.iss`, добавьте их в `VERSION_FILES` в `scripts/version.py`
  по образцу `ApiNgRPC`
