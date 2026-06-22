#!/usr/bin/env python3
"""
Version management script for ApiRgRPC.
Synchronizes versions across all version files.

Source of truth: tauri-app/src-tauri/Cargo.toml [package].version
Targets: npm package.json, Tauri Cargo + tauri.conf.json, README badge.

(ApiRgRPC has no shared-rs/ crate and no installer/, unlike the sibling
ApiNgRPC project this script is modelled on, so those targets are omitted.)

Usage:
    python scripts/version.py status          # Show current versions
    python scripts/version.py check           # Like status, exit 1 on mismatch
    python scripts/version.py sync            # Sync all versions from Cargo.toml
    python scripts/version.py bump patch      # 0.1.0 -> 0.1.1
    python scripts/version.py bump minor      # 0.1.0 -> 0.2.0
    python scripts/version.py bump major      # 0.1.0 -> 1.0.0
    python scripts/version.py set 1.0.0       # Set specific version
"""

import argparse
import json
import re
import sys
from pathlib import Path

# File paths relative to project root
VERSION_FILES = {
    "tauri_cargo": "tauri-app/src-tauri/Cargo.toml",
    "npm": "tauri-app/package.json",
    "tauri_conf": "tauri-app/src-tauri/tauri.conf.json",
    "readme": "README.md",
}

# Canonical source of truth (no shared-rs in ApiRgRPC, so Tauri crate is it).
CANONICAL = "tauri_cargo"

# Shields.io badge in README: .../badge/version-X.Y.Z-blue
# (ApiRgRPC uses the plain "-blue" suffix, not "-blue.svg".)
README_VERSION_BADGE_RE = re.compile(
    r"(https://img\.shields\.io/badge/version-)(\d+\.\d+\.\d+)(-blue)"
)


def get_project_root() -> Path:
    """Find project root by looking for the .git directory."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    # Fallback: assume script is in scripts/
    return Path(__file__).resolve().parent.parent


def _read_text(path: Path) -> str:
    """Read text without translating newlines (so we can preserve them)."""
    return path.read_text(encoding="utf-8", newline="")


def _write_text(path: Path, content: str) -> None:
    """Write text without translating newlines (preserves existing CRLF/LF)."""
    path.write_text(content, encoding="utf-8", newline="")


def read_cargo_version(path: Path) -> str:
    """Read version from Cargo.toml."""
    content = _read_text(path)
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if match:
        return match.group(1)
    raise ValueError(f"Version not found in {path}")


def write_cargo_version(path: Path, version: str) -> None:
    """Write version to Cargo.toml (targeted replace, preserves formatting)."""
    content = _read_text(path)
    new_content, count = re.subn(
        r'^(version\s*=\s*")[^"]+(")',
        rf'\g<1>{version}\g<2>',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise ValueError(f"Version line not found in {path}")
    _write_text(path, new_content)


# Top-level JSON "version": "X.Y.Z" line. Targeted replace keeps the file's
# formatting, key order, and CRLF line endings intact (json.dump would not).
JSON_VERSION_RE = re.compile(r'("version"\s*:\s*")[^"]+(")')


def read_json_version(path: Path) -> str:
    """Read version from a JSON manifest."""
    data = json.loads(_read_text(path))
    return data.get("version", "0.0.0")


def write_json_version(path: Path, version: str) -> None:
    """Write version to a JSON manifest (targeted replace, preserves formatting)."""
    content = _read_text(path)
    new_content, count = JSON_VERSION_RE.subn(
        rf'\g<1>{version}\g<2>',
        content,
        count=1,
    )
    if count != 1:
        raise ValueError(f'Top-level "version" not found in {path}')
    _write_text(path, new_content)


# Backwards-compatible aliases (npm + tauri.conf use identical JSON handling).
read_package_json_version = read_json_version
write_package_json_version = write_json_version
read_tauri_conf_version = read_json_version
write_tauri_conf_version = write_json_version


def read_readme_version(path: Path) -> str:
    """Read app version from README.md Shields.io badge."""
    content = _read_text(path)
    match = README_VERSION_BADGE_RE.search(content)
    if match:
        return match.group(2)
    return "0.0.0"


def write_readme_version(path: Path, version: str) -> None:
    """Update version in README.md Shields.io badge (must match README_VERSION_BADGE_RE)."""
    content = _read_text(path)
    new_content, count = README_VERSION_BADGE_RE.subn(
        rf"\g<1>{version}\g<3>",
        content,
        count=1,
    )
    if count != 1:
        raise ValueError(
            f"Expected exactly one Shields version badge in {path} "
            f"(pattern: .../badge/version-X.Y.Z-blue)"
        )
    _write_text(path, new_content)


def get_all_versions(root: Path) -> dict[str, str]:
    """Get versions from all files that exist."""
    versions = {}

    tauri_cargo_path = root / VERSION_FILES["tauri_cargo"]
    if tauri_cargo_path.exists():
        versions["tauri_cargo"] = read_cargo_version(tauri_cargo_path)

    npm_path = root / VERSION_FILES["npm"]
    if npm_path.exists():
        versions["npm"] = read_package_json_version(npm_path)

    tauri_conf_path = root / VERSION_FILES["tauri_conf"]
    if tauri_conf_path.exists():
        versions["tauri_conf"] = read_tauri_conf_version(tauri_conf_path)

    readme_path = root / VERSION_FILES["readme"]
    if readme_path.exists():
        versions["readme"] = read_readme_version(readme_path)

    return versions


def set_all_versions(root: Path, version: str) -> None:
    """Set version in all files that exist."""
    tauri_cargo_path = root / VERSION_FILES["tauri_cargo"]
    if tauri_cargo_path.exists():
        write_cargo_version(tauri_cargo_path, version)
        print(f"  [OK] {VERSION_FILES['tauri_cargo']}: {version}")

    npm_path = root / VERSION_FILES["npm"]
    if npm_path.exists():
        write_package_json_version(npm_path, version)
        print(f"  [OK] {VERSION_FILES['npm']}: {version}")

    tauri_conf_path = root / VERSION_FILES["tauri_conf"]
    if tauri_conf_path.exists():
        write_tauri_conf_version(tauri_conf_path, version)
        print(f"  [OK] {VERSION_FILES['tauri_conf']}: {version}")

    readme_path = root / VERSION_FILES["readme"]
    if readme_path.exists():
        write_readme_version(readme_path, version)
        print(f"  [OK] {VERSION_FILES['readme']}: {version}")


def bump_version(version: str, bump_type: str) -> str:
    """Bump version according to semver."""
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {version}")

    major, minor, patch = map(int, parts)

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "patch":
        patch += 1
    else:
        raise ValueError(f"Unknown bump type: {bump_type}")

    return f"{major}.{minor}.{patch}"


def cmd_status(root: Path) -> bool:
    """Show current version status. Returns True if all in sync."""
    print("[Version] ApiRgRPC Version Status")
    print("=" * 50)

    versions = get_all_versions(root)
    if not versions:
        print("[!] No version files found")
        return False

    unique_versions = set(versions.values())
    canonical = versions.get(CANONICAL)
    if canonical is None:
        print(f"[!] {VERSION_FILES[CANONICAL]} missing — cannot determine source version")
        canonical = next(iter(versions.values()), "0.0.0")

    max_path_len = max(len(VERSION_FILES.get(name, name)) for name in versions)

    for name, version in versions.items():
        file_path = VERSION_FILES.get(name, name)
        status = "[OK]" if version == canonical else "[!]"
        print(f"  {file_path.ljust(max_path_len)} : {version} {status}")

    print()
    in_sync = len(unique_versions) == 1
    if in_sync:
        print("[OK] All versions synchronized")
    else:
        print("[!] Versions out of sync!")
        print()
        print("To fix, run:")
        print("  python scripts/version.py sync")
    return in_sync


def cmd_sync(root: Path, target_version: str | None = None) -> None:
    """Synchronize all versions."""
    if target_version:
        version = target_version
    else:
        canonical_path = root / VERSION_FILES[CANONICAL]
        version = read_cargo_version(canonical_path)

    print(f"[Sync] Syncing all files to version {version}")
    set_all_versions(root, version)
    print("[OK] Done!")


def cmd_bump(root: Path, bump_type: str) -> None:
    """Bump version."""
    canonical_path = root / VERSION_FILES[CANONICAL]
    current = read_cargo_version(canonical_path)
    new_version = bump_version(current, bump_type)

    print(f"[Bump] Bumping version: {current} -> {new_version}")
    set_all_versions(root, new_version)
    print("[OK] Done!")


def cmd_set(root: Path, version: str) -> None:
    """Set specific version."""
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        print(f"[ERROR] Invalid version format: {version}")
        print("   Expected: X.Y.Z (e.g., 1.0.0)")
        sys.exit(1)

    print(f"[Set] Setting version to {version}")
    set_all_versions(root, version)
    print("[OK] Done!")


def main() -> None:
    parser = argparse.ArgumentParser(description="ApiRgRPC version management")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show version status")
    subparsers.add_parser("check", help="Show version status, exit 1 if out of sync")

    sync_parser = subparsers.add_parser("sync", help="Sync all versions")
    sync_parser.add_argument("version", nargs="?", help="Target version (optional)")

    bump_parser = subparsers.add_parser("bump", help="Bump version")
    bump_parser.add_argument("type", choices=["major", "minor", "patch"])

    set_parser = subparsers.add_parser("set", help="Set specific version")
    set_parser.add_argument("version", help="Version to set (X.Y.Z)")

    args = parser.parse_args()
    root = get_project_root()

    if args.command == "status":
        cmd_status(root)
    elif args.command == "check":
        if not cmd_status(root):
            sys.exit(1)
    elif args.command == "sync":
        cmd_sync(root, args.version)
    elif args.command == "bump":
        cmd_bump(root, args.type)
    elif args.command == "set":
        cmd_set(root, args.version)


if __name__ == "__main__":
    main()
