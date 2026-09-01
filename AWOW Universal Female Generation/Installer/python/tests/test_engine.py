from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "Installer" / "python"))

from ufg_installer.core import Installer
from ufg_installer.discovery import parse_libraryfolders, select_target


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class EngineTests(unittest.TestCase):
    ck3 = b"fixture ck3 executable"
    steam = b"fixture steam dxcompiler"
    agp_proxy = b"fixture compatible agp proxy"
    agp_payload = b"fixture compatible agp payload"
    ufg_proxy = b"fixture ufg proxy"
    ufg_payload = b"fixture ufg payload"

    def make_package(
        self,
        root: Path,
        *,
        package_name: str = "release package with spaces",
        version: str = "1.0.0",
        ck3: bytes | None = None,
        steam: bytes | None = None,
        agp_proxy: bytes | None = None,
        agp_payload: bytes | None = None,
        ufg_proxy: bytes | None = None,
        ufg_payload: bytes | None = None,
    ) -> Path:
        ck3 = self.ck3 if ck3 is None else ck3
        steam = self.steam if steam is None else steam
        agp_proxy = self.agp_proxy if agp_proxy is None else agp_proxy
        agp_payload = self.agp_payload if agp_payload is None else agp_payload
        ufg_proxy = self.ufg_proxy if ufg_proxy is None else ufg_proxy
        ufg_payload = self.ufg_payload if ufg_payload is None else ufg_payload
        package = root / package_name
        (package / "Installer").mkdir(parents=True)
        (package / "build").mkdir()
        (package / "build" / "AWOW Universal Female Generation").mkdir(parents=True)
        (package / "dxcompiler.dll").write_bytes(ufg_proxy)
        (package / "AWOW Universal Female Generation" ).mkdir()
        (package / "AWOW Universal Female Generation" / "awow_ufg.dll").write_bytes(ufg_payload)
        (package / "build" / "dxcompiler.dll").write_bytes(ufg_proxy)
        (package / "build" / "AWOW Universal Female Generation" / "awow_ufg.dll").write_bytes(ufg_payload)
        manifest = json.loads((ROOT / "Installer" / "release-manifest.json").read_text(encoding="utf-8"))
        manifest["release"]["version"] = version
        manifest["target"]["supported_builds"][0].update({"executable_sha256": digest(ck3), "original_dxcompiler_sha256": digest(steam)})
        manifest["artifacts"][0].update({"sha256": digest(ufg_proxy), "size_bytes": len(ufg_proxy)})
        manifest["artifacts"][1].update({"sha256": digest(ufg_payload), "size_bytes": len(ufg_payload)})
        candidate = manifest["compatible_agp_builds"][0]
        candidate.update({"executable_sha256": digest(ck3), "proxy_sha256": digest(agp_proxy), "payload_sha256": digest(agp_payload), "original_dxcompiler_sha256": digest(steam)})
        for seed in manifest["compatibility"]["seeds"]:
            for item in seed["match"].get("required_files", []):
                relative = item["relative_path"]
                if relative == "dxcompiler.dll":
                    value = ufg_proxy if seed["state"] in {"manual_ufg", "managed_ufg", "ufg_proxy_only"} else agp_proxy
                    item.update({"sha256": digest(value), "size_bytes": len(value)})
                elif relative == "dxcompiler_original.dll":
                    item.update({"sha256": digest(steam), "size_bytes": len(steam)})
                elif relative == "AGP Native Hook/agp_parenthook.dll":
                    item.update({"sha256": digest(agp_payload), "size_bytes": len(agp_payload)})
                elif relative == "AWOW Universal Female Generation/awow_ufg.dll":
                    item.update({"sha256": digest(ufg_payload), "size_bytes": len(ufg_payload)})
        (package / "Installer" / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return package

    def make_target(self, root: Path, *, ufg: bool = False, proxy_only: bool = False) -> Path:
        target = root / "Steam Library" / "steamapps" / "common" / "Crusader Kings III" / "binaries"
        target.mkdir(parents=True)
        (target / "ck3.exe").write_bytes(self.ck3)
        (target / "dxcompiler.dll").write_bytes(self.ufg_proxy if ufg else self.agp_proxy)
        (target / "dxcompiler_original.dll").write_bytes(self.steam)
        (target / "AGP Native Hook").mkdir()
        (target / "AGP Native Hook" / "agp_parenthook.dll").write_bytes(self.agp_payload)
        if ufg and not proxy_only:
            (target / "AWOW Universal Female Generation").mkdir()
            (target / "AWOW Universal Female Generation" / "awow_ufg.dll").write_bytes(self.ufg_payload)
        return target

    def engine(self, package: Path, **kwargs) -> Installer:
        return Installer(package_root=package, process_checker=lambda: False, **kwargs)

    def test_fresh_install_and_proxy_only_uninstall_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = self.make_package(root)
            target = self.make_target(root)
            engine = self.engine(package)
            self.assertEqual(engine.classify(target).state, "agp_ready")
            installed = engine.install(target)
            self.assertEqual(installed.decision, "proceed", installed.message)
            self.assertEqual(engine.classify(target).state, "managed_ufg")
            active_before = (target / "dxcompiler.dll").read_bytes()
            original_before = (target / "dxcompiler_original.dll").read_bytes()
            agp_before = (target / "AGP Native Hook" / "agp_parenthook.dll").read_bytes()
            removed = engine.uninstall(target)
            self.assertEqual(removed.decision, "proceed", removed.message)
            self.assertEqual((target / "dxcompiler.dll").read_bytes(), active_before)
            self.assertEqual((target / "dxcompiler_original.dll").read_bytes(), original_before)
            self.assertEqual((target / "AGP Native Hook" / "agp_parenthook.dll").read_bytes(), agp_before)
            state = json.loads((target / "AWOW Universal Female Generation" / "ufg-install-state.json").read_text())
            self.assertEqual(state["status"], "ufg_proxy_only")
            self.assertFalse((target / "AWOW Universal Female Generation" / "awow_ufg.dll").exists())
            self.assertEqual(engine.classify(target).state, "ufg_proxy_only")

    def test_fresh_install_requires_exact_agp_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = self.make_package(root)
            target = self.make_target(root)
            (target / "AGP Native Hook" / "agp_parenthook.dll").write_bytes(b"wrong AGP payload")
            before = {p: p.read_bytes() for p in (target / "dxcompiler.dll", target / "dxcompiler_original.dll")}
            result = self.engine(package).install(target)
            self.assertEqual(result.decision, "reject")
            self.assertIn("compatible AGP", result.message)
            self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_manual_layout_adoption_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = self.make_package(root)
            target = self.make_target(root, ufg=True)
            engine = self.engine(package)
            request = engine.install_confirmation(target)
            self.assertEqual((request.kind, request.token), ("manual_adoption", "ADOPT_UFG_LAYOUT"))
            self.assertIn("installed manually", request.message)
            refused = engine.install(target)
            self.assertEqual(refused.decision, "abort")
            adopted = engine.install(target, "ADOPT_UFG_LAYOUT")
            self.assertEqual(adopted.decision, "proceed", adopted.message)
            self.assertEqual(engine.classify(target).state, "managed_ufg")

    def test_proxy_only_reenable_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = self.make_package(root)
            target = self.make_target(root)
            engine = self.engine(package)
            engine.install(target)
            engine.uninstall(target)
            request = engine.install_confirmation(target)
            self.assertEqual((request.kind, request.token), ("proxy_only_reenable", "RE_ENABLE_UFG"))
            self.assertIn("payload was removed", request.message)
            refused = engine.install(target)
            self.assertEqual(refused.decision, "abort")
            enabled = engine.install(target, "RE_ENABLE_UFG")
            self.assertEqual(enabled.decision, "proceed", enabled.message)
            self.assertEqual(engine.classify(target).state, "managed_ufg")

    def test_managed_upgrade_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = self.make_package(root)
            target = self.make_target(root)
            engine = self.engine(package)
            engine.install(target)
            request = engine.install_confirmation(target)
            self.assertEqual((request.kind, request.token), ("managed_upgrade", "UPGRADE_UFG_IN_PLACE"))
            self.assertIn("already managed", request.message)
            refused = engine.install(target)
            self.assertEqual(refused.decision, "abort")
            self.assertEqual(engine.install(target, "UPGRADE_UFG_IN_PLACE").decision, "proceed")

    def test_uninstall_refuses_payload_drift_without_touching_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = self.make_package(root)
            target = self.make_target(root)
            engine = self.engine(package)
            engine.install(target)
            (target / "AWOW Universal Female Generation" / "awow_ufg.dll").write_bytes(b"drifted")
            active = (target / "dxcompiler.dll").read_bytes()
            result = engine.uninstall(target)
            self.assertEqual(result.decision, "reject")
            self.assertEqual((target / "dxcompiler.dll").read_bytes(), active)

    def test_write_fault_rolls_back_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = self.make_package(root)
            target = self.make_target(root)
            before = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()}
            engine = self.engine(package, write_fault_at="AWOW Universal Female Generation/awow_ufg.dll")
            result = engine.install(target)
            self.assertEqual(result.decision, "rollback", result.message)
            after = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()}
            self.assertEqual(after, before)

    def test_running_game_is_rejected_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = self.make_package(root)
            target = self.make_target(root)
            engine = Installer(package_root=package, process_checker=lambda: True)
            with self.assertRaises(Exception):
                engine.install(target)

    def test_orphan_ufg_proxy_is_not_misclassified_as_agp_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = self.make_package(root)
            target = self.make_target(root, ufg=True, proxy_only=True)
            engine = self.engine(package)
            classification = engine.classify(target)
            self.assertEqual(classification.state, "unknown_conflicting")
            self.assertIn("without state or payload", classification.reason)

    def test_unknown_files_and_agp_state_survive_install_and_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = self.make_package(root)
            target = self.make_target(root)
            unknown = target / "AWOW Universal Female Generation" / "maintainer-note.txt"
            unknown.parent.mkdir(parents=True)
            unknown.write_bytes(b"do not remove")
            agp_state = {
                "schema_version": 1,
                "kind": "agp_install_state",
                "status": "managed_agp",
                "baseline": {"original_dxcompiler": {"sha256": digest(self.steam)}},
                "managed_files": [
                    {"relative_path": "dxcompiler.dll", "ownership": "managed", "installed_sha256": digest(self.agp_proxy)},
                    {"relative_path": "AGP Native Hook/agp_parenthook.dll", "ownership": "managed", "installed_sha256": digest(self.agp_payload)},
                ],
            }
            agp_state_path = target / "AGP Native Hook" / "agp-install-state.json"
            agp_state_path.write_text(json.dumps(agp_state, indent=2) + "\n", encoding="utf-8")
            agp_state_before = agp_state_path.read_bytes()
            engine = self.engine(package)
            self.assertEqual(engine.install(target).decision, "proceed")
            self.assertEqual(unknown.read_bytes(), b"do not remove")
            self.assertEqual(agp_state_path.read_bytes(), agp_state_before)
            self.assertEqual(engine.uninstall(target).decision, "proceed")
            self.assertEqual(unknown.read_bytes(), b"do not remove")
            self.assertEqual(agp_state_path.read_bytes(), agp_state_before)

    def test_changed_hash_managed_upgrade_replaces_both_ufg_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_package = self.make_package(root, package_name="old release")
            new_proxy, new_payload = b"fixture ufg proxy v2", b"fixture ufg payload v2"
            new_package = self.make_package(root, package_name="new release", version="1.1.0", ufg_proxy=new_proxy, ufg_payload=new_payload)
            target = self.make_target(root)
            self.assertEqual(self.engine(old_package).install(target).decision, "proceed")
            new_engine = self.engine(new_package)
            self.assertEqual(new_engine.classify(target).state, "managed_ufg")
            self.assertEqual(new_engine.install(target).decision, "abort")
            upgraded = new_engine.install(target, "UPGRADE_UFG_IN_PLACE")
            self.assertEqual(upgraded.decision, "proceed", upgraded.message)
            self.assertEqual((target / "dxcompiler.dll").read_bytes(), new_proxy)
            self.assertEqual((target / "AWOW Universal Female Generation" / "awow_ufg.dll").read_bytes(), new_payload)

    def test_changed_hash_proxy_only_upgrade_requires_upgrade_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_package = self.make_package(root, package_name="old release")
            new_proxy, new_payload = b"fixture ufg proxy v2", b"fixture ufg payload v2"
            new_package = self.make_package(root, package_name="new release", version="1.1.0", ufg_proxy=new_proxy, ufg_payload=new_payload)
            target = self.make_target(root)
            old_engine = self.engine(old_package)
            self.assertEqual(old_engine.install(target).decision, "proceed")
            self.assertEqual(old_engine.uninstall(target).decision, "proceed")
            new_engine = self.engine(new_package)
            self.assertEqual(new_engine.classify(target).state, "ufg_proxy_only")
            request = new_engine.install_confirmation(target)
            self.assertEqual((request.kind, request.token), ("proxy_only_cross_release", "UPGRADE_UFG_IN_PLACE"))
            self.assertIn("older UFG proxy", request.message)
            refused = new_engine.install(target, "RE_ENABLE_UFG")
            self.assertEqual(refused.decision, "abort")
            upgraded = new_engine.install(target, "UPGRADE_UFG_IN_PLACE")
            self.assertEqual(upgraded.decision, "proceed", upgraded.message)
            self.assertEqual((target / "dxcompiler.dll").read_bytes(), new_proxy)
            self.assertEqual((target / "AWOW Universal Female Generation" / "awow_ufg.dll").read_bytes(), new_payload)

    def test_agp_replacement_after_disable_allows_matching_ufg_reenable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_package = self.make_package(root, package_name="old release")
            target = self.make_target(root)
            old_engine = self.engine(old_package)
            self.assertEqual(old_engine.install(target).decision, "proceed")
            self.assertEqual(old_engine.uninstall(target).decision, "proceed")

            new_ck3, new_steam = b"fixture ck3 executable v2", b"fixture steam dxcompiler v2"
            new_agp_proxy, new_agp_payload = b"fixture compatible agp proxy v2", b"fixture compatible agp payload v2"
            new_ufg_proxy, new_ufg_payload = b"fixture ufg proxy v2", b"fixture ufg payload v2"
            new_package = self.make_package(
                root,
                package_name="new release",
                version="1.1.0",
                ck3=new_ck3,
                steam=new_steam,
                agp_proxy=new_agp_proxy,
                agp_payload=new_agp_payload,
                ufg_proxy=new_ufg_proxy,
                ufg_payload=new_ufg_payload,
            )
            (target / "ck3.exe").write_bytes(new_ck3)
            (target / "dxcompiler_original.dll").write_bytes(new_steam)
            (target / "dxcompiler.dll").write_bytes(new_agp_proxy)
            (target / "AGP Native Hook" / "agp_parenthook.dll").write_bytes(new_agp_payload)

            new_engine = self.engine(new_package)
            self.assertEqual(new_engine.classify(target).state, "ufg_proxy_only")
            request = new_engine.install_confirmation(target)
            self.assertEqual((request.kind, request.token), ("proxy_only_after_agp_replacement", "RE_ENABLE_UFG"))
            self.assertIn("standalone AGP proxy", request.message)
            self.assertEqual(new_engine.install(target).decision, "abort")
            enabled = new_engine.install(target, "RE_ENABLE_UFG")
            self.assertEqual(enabled.decision, "proceed", enabled.message)
            self.assertEqual((target / "dxcompiler.dll").read_bytes(), new_ufg_proxy)
            self.assertEqual((target / "AWOW Universal Female Generation" / "awow_ufg.dll").read_bytes(), new_ufg_payload)

    def test_new_installer_uninstalls_old_owned_payload_without_relabeling_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_package = self.make_package(root, package_name="old release")
            new_package = self.make_package(root, package_name="new release", version="1.1.0", ufg_proxy=b"fixture ufg proxy v2", ufg_payload=b"fixture ufg payload v2")
            target = self.make_target(root)
            self.assertEqual(self.engine(old_package).install(target).decision, "proceed")
            old_proxy = (target / "dxcompiler.dll").read_bytes()
            new_engine = self.engine(new_package)
            removed = new_engine.uninstall(target)
            self.assertEqual(removed.decision, "proceed", removed.message)
            self.assertEqual((target / "dxcompiler.dll").read_bytes(), old_proxy)
            self.assertEqual(new_engine.classify(target).state, "ufg_proxy_only")

    def test_discovery_and_manual_selection(self) -> None:
        values = parse_libraryfolders('"libraryfolders" { "0" { "path" "C:\\\\Steam" } }')
        self.assertEqual(values, [Path("C:\\Steam")])
        self.assertEqual(select_target("C:/Games/Crusader Kings III").name, "binaries")


if __name__ == "__main__":
    unittest.main()
