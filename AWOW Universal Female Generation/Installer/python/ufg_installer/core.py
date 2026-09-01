"""Transactional AWOW Universal Female Generation installer core.

UFG is an optional payload chained behind Any-Gender Parenthook (AGP).  This
module owns only UFG's proxy, payload, logs, state, and transaction folders.
It deliberately reads and verifies AGP files but never replaces, removes, or
writes them.  The PowerShell engine implements the same contract separately.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .paths import PathSafetyError, assert_no_reparse_ancestors, contained, is_reparse, validate_relative


class InstallError(RuntimeError):
    """A safe, user-facing operation failure."""


@dataclass(frozen=True)
class Classification:
    state: str
    reason: str = ""
    state_data: dict[str, Any] | None = None
    state_valid: bool = False


@dataclass(frozen=True)
class ConfirmationRequest:
    kind: str
    token: str
    title: str
    message: str


@dataclass
class Result:
    operation: str
    decision: str
    classification: str
    next_state: str
    transaction_id: str | None = None
    message: str = ""
    journal: Path | None = None
    changed: list[str] = field(default_factory=list)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_hash(path: Path) -> str:
    return _sha256(path)


def _observation(path: Path) -> dict[str, Any]:
    if not path.exists() and not path.is_symlink():
        return {"exists": False, "kind": "absent"}
    if is_reparse(path):
        raise InstallError(f"reparse point is not an authorized file: {path}")
    if path.is_dir():
        return {"exists": True, "kind": "directory", "is_reparse_point": False}
    if path.is_file():
        stat = path.stat()
        return {"exists": True, "kind": "file", "sha256": _sha256(path), "size_bytes": stat.st_size, "is_reparse_point": False}
    raise InstallError(f"unsupported target path: {path}")


def _same_file(path: Path, sha: str, size: int | None = None) -> bool:
    try:
        return path.is_file() and (size is None or path.stat().st_size == size) and _sha256(path) == str(sha).lower()
    except (OSError, ValueError):
        return False


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        # Windows PowerShell 5.1 historically emits UTF-8 BOMs for
        # Set-Content.  Accept both BOM and BOM-less package contracts.
        with path.open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError("JSON root is not an object")
        return value
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise InstallError(f"invalid JSON: {path}") from exc


def _required(value: object, *keys: str) -> bool:
    return isinstance(value, dict) and all(key in value for key in keys)


def _is_uuid(value: object) -> bool:
    try:
        uuid.UUID(str(value), version=4)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdefABCDEF" for char in value)


def _valid_baseline(item: object, relative: str) -> bool:
    return (
        isinstance(item, dict)
        and item.get("relative_path") == relative
        and _is_sha(item.get("sha256"))
        and isinstance(item.get("size_bytes"), int)
        and item["size_bytes"] >= 0
        and item.get("ownership") == "steam"
    )


def _is_valid_state(data: object, *, active_rel: str = "dxcompiler.dll", payload_rel: str = "AWOW Universal Female Generation/awow_ufg.dll", original_rel: str = "dxcompiler_original.dll", state_rel: str = "AWOW Universal Female Generation/ufg-install-state.json") -> bool:
    """Validate the durable state shape without trusting it for ownership."""

    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("kind") != "ufg_install_state":
        return False
    status = data.get("status")
    if status not in {"managed_ufg", "ufg_proxy_only"} or not _is_uuid(data.get("transaction_id")):
        return False
    release = data.get("release")
    if not isinstance(release, dict) or release.get("id") != "awow-ufg" or not _is_sha(release.get("manifest_sha256")):
        return False
    if not isinstance(release.get("version"), str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", release["version"]) is None:
        return False
    target = data.get("target")
    if not isinstance(target, dict) or target.get("game_id") != "crusader_kings_iii" or target.get("binaries_relative_path") != "binaries" or target.get("executable_relative_path") != "ck3.exe" or target.get("target_root_kind") != "steam_game_binaries":
        return False
    baseline = data.get("baseline")
    if not isinstance(baseline, dict) or not _valid_baseline(baseline.get("original_dxcompiler"), original_rel) or not _valid_baseline(baseline.get("executable"), "ck3.exe"):
        return False
    dependency = data.get("agp_dependency")
    if not isinstance(dependency, dict) or dependency.get("proxy_relative_path") != active_rel or dependency.get("payload_relative_path") != "AGP Native Hook/agp_parenthook.dll" or dependency.get("state_relative_path") != "AGP Native Hook/agp-install-state.json" or not _is_sha(dependency.get("proxy_sha256")) or not _is_sha(dependency.get("payload_sha256")) or not _is_sha(dependency.get("original_dxcompiler_sha256")) or dependency.get("state_sha256") != "absent" and not _is_sha(dependency.get("state_sha256")):
        return False
    managed = data.get("managed_files")
    if not isinstance(managed, list) or len(managed) != 2:
        return False
    roles: set[str] = set()
    expected_roles = {active_rel: "ufg_proxy", payload_rel: "ufg_payload"}
    expected_restore = {active_rel: "leave_managed_file", payload_rel: "remove_managed_file"}
    for item in managed:
        if not isinstance(item, dict) or item.get("ownership") != "managed" or item.get("role") not in {"ufg_proxy", "ufg_payload"} or item.get("relative_path") not in {active_rel, payload_rel} or item.get("relative_path") in roles or not _is_sha(item.get("installed_sha256")) or not isinstance(item.get("installed_size_bytes"), int) or item["installed_size_bytes"] < 0 or not isinstance(item.get("present"), bool):
            return False
        restore = item.get("restore")
        if not isinstance(restore, dict) or item["role"] != expected_roles[item["relative_path"]] or restore.get("action") != expected_restore[item["relative_path"]]:
            return False
        roles.add(item["relative_path"])
    if roles != {active_rel, payload_rel}:
        return False
    present = {item["relative_path"]: item["present"] for item in managed}
    if not present[active_rel] or present[payload_rel] != (status == "managed_ufg"):
        return False
    quarantined = data.get("quarantined_files")
    if not isinstance(quarantined, list):
        return False
    if any(not isinstance(item, dict) for item in quarantined):
        return False
    foreign = data.get("foreign_cleanup")
    if not isinstance(foreign, dict) or foreign.get("kind") != "none" or foreign.get("removed_paths") != [] or foreign.get("uninstall_policy") != "none" or not isinstance(foreign.get("quarantine_relative_path"), str):
        return False
    try:
        validate_relative(foreign["quarantine_relative_path"])
    except (PathSafetyError, TypeError):
        return False
    if not isinstance(data.get("created_utc"), str) or not isinstance(data.get("updated_utc"), str):
        return False
    return True


def _is_process_running() -> bool:
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ck3.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=3, check=False)
        return any("ck3.exe" in line.casefold() and "no tasks" not in line.casefold() for line in result.stdout.splitlines())
    except (OSError, subprocess.SubprocessError):
        return False


def frozen_package_root() -> Path | None:
    """Locate the unpacked package from either release-root or dev EXEs."""

    if not getattr(sys, "frozen", False):
        return None
    executable_dir = Path(sys.executable).resolve().parent
    for candidate in (executable_dir, executable_dir.parent):
        if (candidate / "Installer" / "release-manifest.json").is_file():
            return candidate
    return executable_dir


class _Transaction:
    def __init__(self, engine: "Installer", target: Path, operation: str, source_state: str, target_state: str):
        self.engine = engine
        self.target = target
        self.operation = operation
        self.source_state = source_state
        self.target_state = target_state
        self.id = str(uuid.uuid4())
        self.journal_dir = contained(target, f"AWOW Universal Female Generation/.ufg-journal/{self.id}")
        self.journal_path = contained(target, f"AWOW Universal Female Generation/.ufg-journal/{self.id}.json")
        self.backup_dir = self.journal_dir / "before"
        self.stage_dir = self.journal_dir / "stage"
        self.snapshots: dict[str, bool] = {}
        self.entries: list[dict[str, Any]] = []
        self.phase = "validate"
        self.ufg_root_existed = self._path("AWOW Universal Female Generation").exists()

    def _path(self, relative: str) -> Path:
        return contained(self.target, relative)

    def snapshot(self, relative: str) -> None:
        validate_relative(relative)
        if relative in self.snapshots:
            return
        source = self._path(relative)
        exists = source.exists() or source.is_symlink()
        self.snapshots[relative] = exists
        if exists:
            destination = self.backup_dir / Path(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)

    def entry(self, relative: str, operation: str, ownership: str | None = None, staged: str | None = None) -> None:
        before = _observation(self._path(relative))
        item: dict[str, Any] = {"relative_path": relative, "kind": before["kind"] if before["exists"] else "file", "operation": operation, "before": before, "staged_relative_path": staged or f"AWOW Universal Female Generation/.ufg-journal/{self.id}/stage/{relative}"}
        if ownership:
            item["ownership"] = ownership
        self.entries.append(item)

    def write_journal(self, preserved_agp: dict[str, Any] | None = None) -> None:
        self.phase = "journal"
        journal: dict[str, Any] = {
            "$schema": "https://awow-ufg.invalid/schema/install-journal-v1.json",
            "schema_version": 1,
            "kind": "ufg_install_journal",
            "transaction_id": self.id,
            "operation": self.operation,
            "source_state": self.source_state,
            "target_state": self.target_state,
            "phase": self.phase,
            "target": {"game_id": "crusader_kings_iii", "build_id": self.engine.build_id, "binaries_relative_path": "binaries", "target_root_kind": "steam_game_binaries"},
            "entries": self.entries,
        }
        if preserved_agp is not None:
            journal["preserved_agp"] = preserved_agp
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        _write_json(self.journal_path, journal)

    def update_phase(self, phase: str) -> None:
        self.phase = phase
        if self.journal_path.exists():
            data = _read_json(self.journal_path)
            data["phase"] = phase
            _write_json(self.journal_path, data)

    def _remove(self, path: Path) -> None:
        if path.exists() or path.is_symlink():
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()

    def rollback(self) -> bool:
        try:
            self.update_phase("rollback")
            for relative in sorted(self.snapshots, key=len, reverse=True):
                self._remove(self._path(relative))
            for relative in sorted(self.snapshots, key=len):
                if not self.snapshots[relative]:
                    continue
                source = self.backup_dir / Path(relative)
                destination = self._path(relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(source, destination)
                else:
                    shutil.copy2(source, destination)
            if self.journal_path.exists():
                self.journal_path.unlink()
            if self.journal_dir.exists():
                shutil.rmtree(self.journal_dir)
            parent = self.journal_dir.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
            if not self.ufg_root_existed:
                root = self._path("AWOW Universal Female Generation")
                if root.exists() and root.is_dir() and not any(root.iterdir()):
                    root.rmdir()
            return True
        except Exception:
            return False

    def commit_cleanup(self) -> None:
        if self.journal_path.exists():
            self.journal_path.unlink()
        if self.journal_dir.exists():
            shutil.rmtree(self.journal_dir)
        parent = self.journal_dir.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()


class Installer:
    """Independent Python engine; ``package_root`` is an unpacked UFG release root."""

    def __init__(self, package_root: str | os.PathLike[str] | None = None, manifest_path: str | os.PathLike[str] | None = None, process_checker: Callable[[], bool] | None = None, write_fault_at: str | None = None):
        here = Path(__file__).resolve()
        if package_root is None:
            package_root = frozen_package_root()
        self.package_root = Path(package_root or here.parents[3]).resolve()
        self.manifest_path = Path(manifest_path or self.package_root / "Installer" / "release-manifest.json").resolve()
        self.manifest = _read_json(self.manifest_path)
        if self.manifest.get("schema_version") != 1 or self.manifest.get("kind") != "ufg_release_manifest":
            raise InstallError("release manifest is not UFG schema-v1")
        self.process_checker = process_checker or _is_process_running
        self.write_fault_at = write_fault_at
        self.target_manifest = self.manifest["target"]
        self.build_id = self.target_manifest["supported_builds"][0]["id"]
        self.supported = self.target_manifest["supported_builds"][0]
        self.artifacts = {item["id"]: item for item in self.manifest["artifacts"]}
        self.compatible_agp_builds = list(self.manifest.get("compatible_agp_builds", []))

    @property
    def active_rel(self) -> str:
        return self.target_manifest["active_dxcompiler_relative_path"]

    @property
    def original_rel(self) -> str:
        return self.target_manifest["original_dxcompiler_relative_path"]

    @property
    def state_rel(self) -> str:
        return self.target_manifest["state_relative_path"]

    @property
    def payload_rel(self) -> str:
        return next(item["relative_path"] for item in self.manifest["artifacts"] if item["role"] == "ufg_payload")

    @property
    def log_paths(self) -> list[str]:
        return [item["relative_path"] for item in self.target_manifest.get("logs", [])]

    def _target_preflight(self, target: Path) -> None:
        target = target.absolute()
        if not target.is_dir() or is_reparse(target):
            raise InstallError("selected target must be an existing, non-reparse directory")
        try:
            assert_no_reparse_ancestors(target)
            paths = ["ck3.exe", self.active_rel, self.original_rel, self.state_rel, self.target_manifest["journal_relative_directory"], self.target_manifest["quarantine_relative_directory"], "AGP Native Hook/agp_parenthook.dll", "AGP Native Hook/agp-install-state.json"] + self.log_paths
            for relative in paths:
                contained(target, relative)
        except PathSafetyError as exc:
            raise InstallError(str(exc)) from exc
        if self.process_checker():
            raise InstallError("ck3.exe is running; close the game before changing UFG files")
        if not _same_file(contained(target, "ck3.exe"), self.supported["executable_sha256"]):
            raise InstallError("selected target is not the supported CK3 executable build")
        journal_root = contained(target, self.target_manifest["journal_relative_directory"])
        if journal_root.exists() and (not journal_root.is_dir() or any(journal_root.iterdir())):
            raise InstallError("an incomplete UFG transaction journal exists; manual recovery is required")
        for artifact in self.artifacts.values():
            source = self._artifact_source(str(artifact["id"]))
            if not _same_file(source, artifact["sha256"], artifact.get("size_bytes")):
                raise InstallError(f"package artifact hash mismatch: {artifact['relative_path']}")

    def _state(self, target: Path) -> tuple[dict[str, Any] | None, bool]:
        path = contained(target, self.state_rel)
        if not path.exists():
            return None, True
        try:
            data = _read_json(path)
        except InstallError:
            return None, False
        return data, _is_valid_state(data, active_rel=self.active_rel, payload_rel=self.payload_rel, original_rel=self.original_rel, state_rel=self.state_rel)

    def _agp_state_valid(self, target: Path, candidate: dict[str, Any]) -> bool:
        path = contained(target, "AGP Native Hook/agp-install-state.json")
        if not path.exists():
            return True
        try:
            data = _read_json(path)
        except InstallError:
            return False
        if data.get("schema_version") != 1 or data.get("kind") != "agp_install_state" or data.get("status") != "managed_agp":
            return False
        baseline = data.get("baseline", {}).get("original_dxcompiler", {})
        if baseline.get("sha256", "").lower() != candidate["original_dxcompiler_sha256"].lower():
            return False
        managed = data.get("managed_files", [])
        expected = {candidate["proxy_relative_path"]: candidate["proxy_sha256"], candidate["payload_relative_path"]: candidate["payload_sha256"]}
        found: dict[str, str] = {}
        for item in managed:
            if isinstance(item, dict) and item.get("relative_path") in expected and item.get("ownership") == "managed":
                found[item["relative_path"]] = str(item.get("installed_sha256", "")).lower()
        return all(found.get(relative) == sha.lower() for relative, sha in expected.items())

    def _managed_item(self, state: dict[str, Any], relative_path: str) -> dict[str, Any] | None:
        for item in state.get("managed_files", []):
            if isinstance(item, dict) and item.get("relative_path") == relative_path:
                return item
        return None

    def _compatible_agp(self, target: Path, *, allowed_active: tuple[str, int] | None = None) -> dict[str, Any] | None:
        for candidate in self.compatible_agp_builds:
            try:
                if not _same_file(contained(target, "ck3.exe"), candidate["executable_sha256"]):
                    continue
                active = contained(target, candidate["proxy_relative_path"])
                if not _same_file(active, candidate["proxy_sha256"]):
                    if allowed_active is None or not _same_file(active, allowed_active[0], allowed_active[1]):
                        continue
                if not _same_file(contained(target, candidate["payload_relative_path"]), candidate["payload_sha256"]):
                    continue
                if not _same_file(contained(target, self.original_rel), candidate["original_dxcompiler_sha256"]):
                    continue
                if not self._agp_state_valid(target, candidate):
                    continue
                return candidate
            except (KeyError, InstallError, PathSafetyError):
                continue
        return None

    def _managed_state_matches(self, target: Path, state: dict[str, Any], dependency: dict[str, Any] | None = None) -> bool:
        if not _is_valid_state(state, active_rel=self.active_rel, payload_rel=self.payload_rel, original_rel=self.original_rel, state_rel=self.state_rel):
            return False
        proxy_item = self._managed_item(state, self.active_rel)
        if proxy_item is None:
            return False
        dependency = dependency or self._compatible_agp(target, allowed_active=(proxy_item["installed_sha256"], proxy_item["installed_size_bytes"]))
        if dependency is None:
            return False
        active_is_agp = _same_file(contained(target, self.active_rel), dependency["proxy_sha256"])
        agp_rebased_proxy_only = state["status"] == "ufg_proxy_only" and active_is_agp and not contained(target, self.payload_rel).exists()
        if not agp_rebased_proxy_only:
            if not _same_file(contained(target, "ck3.exe"), state["baseline"]["executable"]["sha256"], state["baseline"]["executable"]["size_bytes"]):
                return False
            if not _same_file(contained(target, self.original_rel), state["baseline"]["original_dxcompiler"]["sha256"], state["baseline"]["original_dxcompiler"]["size_bytes"]):
                return False
        recorded = state["agp_dependency"]
        if not agp_rebased_proxy_only:
            for key in ("proxy_sha256", "payload_sha256", "original_dxcompiler_sha256"):
                if str(recorded.get(key, "")).lower() != str(dependency[key]).lower():
                    return False
        agp_state_path = contained(target, "AGP Native Hook/agp-install-state.json")
        actual_state_sha = "absent" if not agp_state_path.exists() else _sha256(agp_state_path)
        if not agp_rebased_proxy_only and str(recorded.get("state_sha256", "")).lower() != actual_state_sha.lower():
            return False
        for item in state["managed_files"]:
            path = contained(target, item["relative_path"])
            if item["relative_path"] == self.payload_rel and not item["present"]:
                if path.exists():
                    return False
                continue
            if item["relative_path"] == self.active_rel and agp_rebased_proxy_only:
                continue
            if not item["present"] or not _same_file(path, item["installed_sha256"], item["installed_size_bytes"]):
                return False
        return True

    def classify(self, target: str | os.PathLike[str]) -> Classification:
        root = Path(target).absolute()
        self._target_preflight(root)
        data, valid = self._state(root)
        if data is not None and not valid:
            return Classification("unknown_conflicting", "UFG state is unreadable or not schema-v1; manual recovery is required", data, False)
        if valid and data is not None:
            proxy_item = self._managed_item(data, self.active_rel)
            dependency = self._compatible_agp(root, allowed_active=(proxy_item["installed_sha256"], proxy_item["installed_size_bytes"]) if proxy_item else None)
            if self._managed_state_matches(root, data, dependency):
                return Classification(data["status"], f"UFG state ownership and AGP dependency hashes match ({data['status']})", data, True)
            return Classification("unknown_conflicting", "UFG state or a preserved AGP dependency drifted", data, True)
        incoming_proxy = self.artifacts["ufg-proxy"]
        dependency = self._compatible_agp(root, allowed_active=(incoming_proxy["sha256"], incoming_proxy["size_bytes"]))
        if dependency is None:
            return Classification("unknown_conflicting", "no compatible AGP installation matched the exact manifest hashes; install compatible AGP first", None, valid)
        active = contained(root, self.active_rel)
        payload = contained(root, self.payload_rel)
        if _same_file(active, self.artifacts["ufg-proxy"]["sha256"], self.artifacts["ufg-proxy"].get("size_bytes")) and _same_file(payload, self.artifacts["ufg-payload"]["sha256"], self.artifacts["ufg-payload"].get("size_bytes")):
            return Classification("manual_ufg", "exact UFG manual layout is eligible for explicit state adoption", None, True)
        if _same_file(active, self.artifacts["ufg-proxy"]["sha256"], self.artifacts["ufg-proxy"].get("size_bytes")) and not payload.exists():
            return Classification("unknown_conflicting", "the UFG proxy is present without state or payload ownership", None, True)
        if payload.exists():
            return Classification("unknown_conflicting", "a UFG payload exists without an exact UFG proxy/state ownership interpretation", None, True)
        return Classification("agp_ready", f"compatible AGP build {dependency['id']} matches exact SHA-256 values", None, True)

    def install_confirmation(self, target: str | os.PathLike[str], classification: Classification | None = None) -> ConfirmationRequest | None:
        """Describe an interactive install decision while keeping tokens internal."""

        root = Path(target).absolute()
        classification = classification or self.classify(root)
        safety = self.manifest["safety"]
        if classification.state == "managed_ufg":
            return ConfirmationRequest(
                "managed_upgrade",
                safety["managed_upgrade_confirmation"],
                "UFG is already installed",
                "UFG is already managed here. Continue to replace its proxy and payload with this release?",
            )
        if classification.state == "manual_ufg":
            return ConfirmationRequest(
                "manual_adoption",
                safety["manual_layout_adoption_confirmation"],
                "Existing UFG files found",
                "Matching UFG files were installed manually. Continue to verify them and add installer management without replacing them?",
            )
        if classification.state != "ufg_proxy_only":
            return None

        incoming_proxy = self.artifacts["ufg-proxy"]
        active = contained(root, self.active_rel)
        active_matches_incoming = _same_file(active, incoming_proxy["sha256"], incoming_proxy.get("size_bytes"))
        state_proxy = self._managed_item(classification.state_data, self.active_rel) if classification.state_data else None
        proxy_only_cross_release = (
            not active_matches_incoming
            and state_proxy is not None
            and _same_file(active, state_proxy["installed_sha256"], state_proxy["installed_size_bytes"])
        )
        if proxy_only_cross_release:
            return ConfirmationRequest(
                "proxy_only_cross_release",
                safety["managed_upgrade_confirmation"],
                "Disabled UFG upgrade found",
                "An older UFG proxy remains while UFG is disabled. Continue to replace it and install this release?",
            )
        if active_matches_incoming:
            return ConfirmationRequest(
                "proxy_only_reenable",
                safety["proxy_only_reenable_confirmation"],
                "UFG is currently disabled",
                "The UFG proxy remains, but its payload was removed. Continue to restore the payload and enable UFG?",
            )
        return ConfirmationRequest(
            "proxy_only_after_agp_replacement",
            safety["proxy_only_reenable_confirmation"],
            "Compatible AGP replacement found",
            "UFG is disabled and a compatible standalone AGP proxy is active. Continue to install this UFG proxy and payload?",
        )

    def _artifact_source(self, artifact_id: str) -> Path:
        artifact = self.artifacts[artifact_id]
        for relative in (artifact.get("source_relative_path"), artifact.get("relative_path")):
            if relative:
                path = self.package_root / str(relative).replace("/", os.sep)
                if path.is_file():
                    return path
        raise InstallError(f"package artifact is missing: {artifact_id}")

    def _copy_staged(self, source: Path, destination: Path, relative: str) -> None:
        if self.write_fault_at and self.write_fault_at == relative:
            raise InstallError(f"simulated write failure at {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.stage")
        try:
            shutil.copy2(source, temporary)
            with temporary.open("rb+") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _stage_artifacts(self, tx: _Transaction, artifact_ids: list[str]) -> None:
        tx.stage_dir.mkdir(parents=True, exist_ok=True)
        for artifact_id in artifact_ids:
            artifact = self.artifacts[artifact_id]
            source = self._artifact_source(artifact_id)
            staged = tx.stage_dir / "package" / Path(str(artifact["relative_path"]).replace("/", os.sep))
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staged)
            if not _same_file(staged, artifact["sha256"], artifact.get("size_bytes")):
                raise InstallError(f"staged artifact hash mismatch: {artifact['relative_path']}")

    def _state_for_commit(self, target: Path, tx: _Transaction, dependency: dict[str, Any], status: str, created_utc: str | None = None, owned_state: dict[str, Any] | None = None) -> dict[str, Any]:
        original = _observation(contained(target, self.original_rel))
        executable = _observation(contained(target, "ck3.exe"))
        agp_state_path = contained(target, "AGP Native Hook/agp-install-state.json")
        agp_state_sha = "absent" if not agp_state_path.exists() else _sha256(agp_state_path)
        proxy = self.artifacts["ufg-proxy"]
        payload = self.artifacts["ufg-payload"]
        release = {"id": self.manifest["release"]["id"], "version": self.manifest["release"]["version"], "manifest_sha256": _json_hash(self.manifest_path)}
        if owned_state is not None:
            old_proxy = self._managed_item(owned_state, self.active_rel)
            old_payload = self._managed_item(owned_state, self.payload_rel)
            if old_proxy is None or old_payload is None:
                raise InstallError("owned UFG state is missing managed artifacts")
            proxy = {"sha256": old_proxy["installed_sha256"], "size_bytes": old_proxy["installed_size_bytes"]}
            payload = {"sha256": old_payload["installed_sha256"], "size_bytes": old_payload["installed_size_bytes"]}
            release = dict(owned_state["release"])
        now = _utc()
        return {
            "$schema": "https://awow-ufg.invalid/schema/install-state-v1.json",
            "schema_version": 1,
            "kind": "ufg_install_state",
            "status": status,
            "transaction_id": tx.id,
            "release": release,
            "target": {"game_id": self.target_manifest["game_id"], "build_id": self.build_id, "binaries_relative_path": "binaries", "executable_relative_path": "ck3.exe", "target_root_kind": "steam_game_binaries"},
            "baseline": {"original_dxcompiler": {"relative_path": self.original_rel, "sha256": original["sha256"], "size_bytes": original["size_bytes"], "ownership": "steam"}, "executable": {"relative_path": "ck3.exe", "sha256": executable["sha256"], "size_bytes": executable["size_bytes"], "ownership": "steam"}},
            "agp_dependency": {"build_id": dependency["id"], "version": dependency["version"], "proxy_relative_path": dependency["proxy_relative_path"], "proxy_sha256": dependency["proxy_sha256"].lower(), "payload_relative_path": dependency["payload_relative_path"], "payload_sha256": dependency["payload_sha256"].lower(), "original_dxcompiler_sha256": dependency["original_dxcompiler_sha256"].lower(), "state_relative_path": dependency["state_relative_path"], "state_sha256": agp_state_sha},
            "managed_files": [
                {"relative_path": self.active_rel, "role": "ufg_proxy", "ownership": "managed", "installed_sha256": proxy["sha256"].lower(), "installed_size_bytes": proxy["size_bytes"], "present": True, "restore": {"action": "leave_managed_file"}},
                {"relative_path": self.payload_rel, "role": "ufg_payload", "ownership": "managed", "installed_sha256": payload["sha256"].lower(), "installed_size_bytes": payload["size_bytes"], "present": status == "managed_ufg", "restore": {"action": "remove_managed_file"}},
            ],
            "quarantined_files": [],
            "foreign_cleanup": {"kind": "none", "quarantine_relative_path": self.target_manifest["quarantine_relative_directory"], "removed_paths": [], "uninstall_policy": "none"},
            "created_utc": created_utc or now,
            "updated_utc": now,
        }

    def _preserved_agp_observations(self, target: Path, dependency: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {"dependency_id": dependency["id"], "paths": {}}
        for relative in (self.active_rel, self.original_rel, dependency["payload_relative_path"], dependency["state_relative_path"]):
            result["paths"][relative] = _observation(contained(target, relative))
        return result

    def _write_and_verify_state(self, target: Path, state: dict[str, Any]) -> None:
        if not _is_valid_state(state, active_rel=self.active_rel, payload_rel=self.payload_rel, original_rel=self.original_rel, state_rel=self.state_rel):
            raise InstallError("generated UFG state failed schema-v1 structural validation")
        path = contained(target, self.state_rel)
        _write_json(path, state)
        read_back = _read_json(path)
        if not _is_valid_state(read_back, active_rel=self.active_rel, payload_rel=self.payload_rel, original_rel=self.original_rel, state_rel=self.state_rel):
            raise InstallError("committed UFG state failed schema-v1 verification")

    def _finish_failure(self, tx: _Transaction, classification: Classification, exc: Exception, fallback: str) -> Result:
        if not tx.journal_path.exists():
            tx.write_journal()
        if tx.rollback():
            return Result(tx.operation, "rollback", classification.state, fallback, tx.id, str(exc), tx.journal_path)
        raise InstallError(f"rollback could not be verified; manual recovery required: {exc}") from exc

    def install(self, target: str | os.PathLike[str], confirmation: str | None = None) -> Result:
        root = Path(target).absolute()
        classification = self.classify(root)
        if classification.state == "unknown_conflicting":
            return Result("install", "reject", classification.state, classification.state, message=f"{classification.reason}; install refuses to modify AGP or unknown files")
        incoming_proxy = self.artifacts["ufg-proxy"]
        active_matches_incoming = _same_file(contained(root, self.active_rel), incoming_proxy["sha256"], incoming_proxy.get("size_bytes"))
        state_proxy = self._managed_item(classification.state_data, self.active_rel) if classification.state_data else None
        request = self.install_confirmation(root, classification)
        required = request.token if request else None
        if required and confirmation != required:
            return Result("install", "abort", classification.state, classification.state, message=f"typed confirmation required: {required}")
        allowed_active = (state_proxy["installed_sha256"], state_proxy["installed_size_bytes"]) if state_proxy else (incoming_proxy["sha256"], incoming_proxy["size_bytes"])
        dependency = self._compatible_agp(root, allowed_active=allowed_active)
        if dependency is None:
            return Result("install", "reject", classification.state, classification.state, message="no compatible AGP installation matched exact SHA-256 values; install compatible AGP first")
        replace_proxy = classification.state not in {"manual_ufg"} and not active_matches_incoming
        if classification.state == "managed_ufg":
            replace_proxy = True
        tx = _Transaction(self, root, "install", classification.state, "managed_ufg")
        try:
            for relative in (self.active_rel, self.payload_rel, self.state_rel, *self.log_paths):
                tx.snapshot(relative)
            tx.entry(self.active_rel, "replace" if replace_proxy else "verify_only", "managed", f"AWOW Universal Female Generation/.ufg-journal/{tx.id}/stage/package/{self.active_rel}")
            payload_op = "create" if not tx._path(self.payload_rel).exists() else "replace"
            tx.entry(self.payload_rel, payload_op, "managed", f"AWOW Universal Female Generation/.ufg-journal/{tx.id}/stage/package/{self.payload_rel}")
            tx.entry(self.state_rel, "create" if not tx._path(self.state_rel).exists() else "replace", "managed", f"AWOW Universal Female Generation/.ufg-journal/{tx.id}/stage/state.json")
            preserved_agp = self._preserved_agp_observations(root, dependency)
            tx.write_journal(preserved_agp)
            tx.update_phase("stage")
            artifacts = (["ufg-proxy"] if replace_proxy else []) + ["ufg-payload"]
            self._stage_artifacts(tx, artifacts)
            tx.update_phase("mutate")
            if replace_proxy:
                self._copy_staged(tx.stage_dir / "package" / "dxcompiler.dll", tx._path(self.active_rel), self.active_rel)
            if classification.state != "manual_ufg":
                self._copy_staged(tx.stage_dir / "package" / Path(self.payload_rel.replace("/", os.sep)), tx._path(self.payload_rel), self.payload_rel)
            if not _same_file(tx._path(self.active_rel), self.artifacts["ufg-proxy"]["sha256"], self.artifacts["ufg-proxy"].get("size_bytes")) or not _same_file(tx._path(self.payload_rel), self.artifacts["ufg-payload"]["sha256"], self.artifacts["ufg-payload"].get("size_bytes")):
                raise InstallError("installed UFG artifact verification failed")
            tx.update_phase("verify")
            old_state = classification.state_data if classification.state_data and classification.state_valid else None
            state = self._state_for_commit(root, tx, dependency, "managed_ufg", old_state.get("created_utc") if old_state else None)
            self._write_and_verify_state(root, state)
            for relative, observation in preserved_agp["paths"].items():
                if relative == self.active_rel:
                    continue
                if _observation(contained(root, relative)) != observation:
                    raise InstallError(f"preserved dependency changed: {relative}")
            tx.update_phase("commit")
            tx.commit_cleanup()
            return Result("install", "proceed", classification.state, "managed_ufg", tx.id, "UFG installed", changed=[self.active_rel, self.payload_rel, self.state_rel])
        except Exception as exc:
            return self._finish_failure(tx, classification, exc, classification.state)

    def uninstall(self, target: str | os.PathLike[str], confirmation: str | None = None) -> Result:
        root = Path(target).absolute()
        classification = self.classify(root)
        if classification.state in {"agp_ready", "ufg_proxy_only"}:
            message = "UFG is not enabled; the active UFG proxy and AGP remain unchanged." if classification.state == "ufg_proxy_only" else "UFG is not installed"
            return Result("uninstall", "no_op", classification.state, classification.state, message=message)
        if classification.state != "managed_ufg" or not classification.state_data:
            return Result("uninstall", "reject", classification.state, classification.state, message=f"{classification.reason}; uninstall refuses to change an unowned or drifted proxy")
        state_proxy = self._managed_item(classification.state_data, self.active_rel)
        dependency = self._compatible_agp(root, allowed_active=(state_proxy["installed_sha256"], state_proxy["installed_size_bytes"]) if state_proxy else None)
        if dependency is None or not self._managed_state_matches(root, classification.state_data, dependency):
            return Result("uninstall", "reject", classification.state, classification.state, message="UFG or AGP dependency drifted; active dxcompiler.dll is left unchanged")
        before_active = _observation(contained(root, self.active_rel))
        tx = _Transaction(self, root, "uninstall", classification.state, "ufg_proxy_only")
        try:
            for relative in (self.active_rel, self.payload_rel, self.state_rel, *self.log_paths):
                tx.snapshot(relative)
            tx.entry(self.active_rel, "verify_only", "managed", f"AWOW Universal Female Generation/.ufg-journal/{tx.id}/stage/snapshot/{self.active_rel}")
            tx.entry(self.payload_rel, "remove", "managed", f"AWOW Universal Female Generation/.ufg-journal/{tx.id}/stage/snapshot/{self.payload_rel}")
            for relative in self.log_paths:
                tx.entry(relative, "remove", "managed", f"AWOW Universal Female Generation/.ufg-journal/{tx.id}/stage/snapshot/{relative}")
            tx.entry(self.state_rel, "replace", "managed", f"AWOW Universal Female Generation/.ufg-journal/{tx.id}/stage/state.json")
            preserved_agp = self._preserved_agp_observations(root, dependency)
            tx.write_journal(preserved_agp)
            tx.update_phase("mutate")
            payload = tx._path(self.payload_rel)
            payload_item = self._managed_item(classification.state_data, self.payload_rel)
            if payload_item is None or not _same_file(payload, payload_item["installed_sha256"], payload_item["installed_size_bytes"]):
                raise InstallError("UFG payload hash changed; refusing uninstall")
            payload.unlink()
            for relative in self.log_paths:
                path = tx._path(relative)
                if path.exists():
                    path.unlink()
            if not _same_file(tx._path(self.active_rel), before_active["sha256"], before_active["size_bytes"]):
                raise InstallError("active dxcompiler.dll changed during uninstall")
            preserved_before = tx.entries[0]["before"]
            state = self._state_for_commit(root, tx, dependency, "ufg_proxy_only", classification.state_data.get("created_utc"), classification.state_data)
            self._write_and_verify_state(root, state)
            if tx._path(self.payload_rel).exists() or not _same_file(tx._path(self.active_rel), before_active["sha256"], before_active["size_bytes"]):
                raise InstallError("UFG proxy-only verification failed")
            tx.update_phase("verify")
            # Recheck every AGP-preserved observation before commit.
            for relative, observation in preserved_agp["paths"].items():
                if relative == self.active_rel:
                    continue
                if _observation(contained(root, relative)) != observation:
                    raise InstallError(f"preserved dependency changed: {relative}")
            tx.update_phase("commit")
            tx.commit_cleanup()
            return Result("uninstall", "proceed", classification.state, "ufg_proxy_only", tx.id, "UFG payload disabled; active UFG proxy remains unchanged and AGP continues loading alone", changed=[self.payload_rel, *self.log_paths, self.state_rel])
        except Exception as exc:
            return self._finish_failure(tx, classification, exc, "managed_ufg")
