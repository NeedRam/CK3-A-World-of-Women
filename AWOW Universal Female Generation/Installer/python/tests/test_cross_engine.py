from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class CrossEngineTests(unittest.TestCase):
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
        (package / "build" / "AWOW Universal Female Generation").mkdir(parents=True)
        for path, value in ((package / "dxcompiler.dll", ufg_proxy), (package / "build" / "dxcompiler.dll", ufg_proxy), (package / "AWOW Universal Female Generation" / "awow_ufg.dll", ufg_payload), (package / "build" / "AWOW Universal Female Generation" / "awow_ufg.dll", ufg_payload)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
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

    def run_ps(self, operation: str, target: Path, package: Path, confirmation: str | None = None, fault: str | None = None):
        script = ROOT / "Installer" / ("install.ps1" if operation == "install" else "uninstall.ps1")
        command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-TargetRoot", str(target), "-PackageRoot", str(package), "-SkipElevationCheck", "-Json"]
        if confirmation:
            command.extend(["-Confirmation", confirmation])
        if fault:
            command.extend(["-WriteFaultAt", fault])
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        output = completed.stdout.strip()
        self.assertTrue(output, completed.stderr)
        start, end = output.find("{"), output.rfind("}")
        self.assertGreaterEqual(start, 0, output)
        return completed.returncode, json.loads(output[start : end + 1])

    def assert_state(self, target: Path, status: str) -> None:
        path = target / "AWOW Universal Female Generation" / "ufg-install-state.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        schema = json.loads((ROOT / "Installer" / "spec" / "install-state.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(state)
        self.assertEqual(state["status"], status)

    def test_python_install_powershell_uninstall_preserves_active_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, target = self.make_package(root), self.make_target(root)
            from ufg_installer.core import Installer
            engine = Installer(package_root=package, process_checker=lambda: False)
            self.assertEqual(engine.install(target).decision, "proceed")
            active = (target / "dxcompiler.dll").read_bytes()
            self.assert_state(target, "managed_ufg")
            code, result = self.run_ps("uninstall", target, package)
            self.assertEqual((code, result["decision"], result["next_state"]), (0, "proceed", "ufg_proxy_only"), result)
            self.assertEqual((target / "dxcompiler.dll").read_bytes(), active)
            self.assert_state(target, "ufg_proxy_only")

    def test_powershell_install_python_uninstall_preserves_agp(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, target = self.make_package(root), self.make_target(root)
            agp = (target / "AGP Native Hook" / "agp_parenthook.dll").read_bytes()
            code, result = self.run_ps("install", target, package)
            self.assertEqual((code, result["decision"]), (0, "proceed"), result)
            self.assert_state(target, "managed_ufg")
            from ufg_installer.core import Installer
            removed = Installer(package_root=package, process_checker=lambda: False).uninstall(target)
            self.assertEqual(removed.decision, "proceed", removed.message)
            self.assertEqual((target / "AGP Native Hook" / "agp_parenthook.dll").read_bytes(), agp)
            self.assert_state(target, "ufg_proxy_only")

    def test_powershell_fault_rolls_back_clean_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, target = self.make_package(root), self.make_target(root)
            before = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()}
            code, result = self.run_ps("install", target, package, fault="AWOW Universal Female Generation/awow_ufg.dll")
            self.assertEqual((code, result["decision"]), (1, "rollback"), result)
            after = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()}
            self.assertEqual(after, before)

    def test_both_engines_block_incomplete_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, target = self.make_package(root), self.make_target(root)
            journal = target / "AWOW Universal Female Generation" / ".ufg-journal"
            journal.mkdir(parents=True)
            (journal / "pending.json").write_text("{}", encoding="utf-8")
            from ufg_installer.core import InstallError, Installer
            with self.assertRaises(InstallError):
                Installer(package_root=package, process_checker=lambda: False).install(target)
            code, result = self.run_ps("install", target, package)
            self.assertEqual(code, 2)
            self.assertEqual(result["decision"], "reject")

    def test_manual_adoption_and_proxy_only_reenable_in_powershell(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, target = self.make_package(root), self.make_target(root, ufg=True)
            code, result = self.run_ps("install", target, package)
            self.assertEqual((code, result["decision"]), (2, "abort"), result)
            code, result = self.run_ps("install", target, package, "ADOPT_UFG_LAYOUT")
            self.assertEqual((code, result["decision"]), (0, "proceed"), result)
            code, result = self.run_ps("uninstall", target, package)
            self.assertEqual((code, result["decision"]), (0, "proceed"), result)
            code, result = self.run_ps("install", target, package, "RE_ENABLE_UFG")
            self.assertEqual((code, result["decision"]), (0, "proceed"), result)
            self.assert_state(target, "managed_ufg")

    def test_powershell_rejects_orphan_ufg_proxy_without_state_or_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package, target = self.make_package(root), self.make_target(root, ufg=True, proxy_only=True)
            code, result = self.run_ps("install", target, package)
            self.assertEqual(code, 2)
            self.assertEqual(result["decision"], "reject")
            self.assertEqual(result["classification"], "unknown_conflicting")
            self.assertFalse((target / "AWOW Universal Female Generation" / "ufg-install-state.json").exists())

    def test_python_old_release_powershell_changed_hash_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_package = self.make_package(root, package_name="old release")
            new_proxy, new_payload = b"fixture ufg proxy v2", b"fixture ufg payload v2"
            new_package = self.make_package(root, package_name="new release", version="1.1.0", ufg_proxy=new_proxy, ufg_payload=new_payload)
            target = self.make_target(root)
            from ufg_installer.core import Installer
            self.assertEqual(Installer(package_root=old_package, process_checker=lambda: False).install(target).decision, "proceed")
            code, result = self.run_ps("install", target, new_package, "UPGRADE_UFG_IN_PLACE")
            self.assertEqual((code, result["decision"]), (0, "proceed"), result)
            self.assertEqual((target / "dxcompiler.dll").read_bytes(), new_proxy)
            self.assertEqual((target / "AWOW Universal Female Generation" / "awow_ufg.dll").read_bytes(), new_payload)

    def test_powershell_old_proxy_only_python_changed_hash_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_package = self.make_package(root, package_name="old release")
            new_proxy, new_payload = b"fixture ufg proxy v2", b"fixture ufg payload v2"
            new_package = self.make_package(root, package_name="new release", version="1.1.0", ufg_proxy=new_proxy, ufg_payload=new_payload)
            target = self.make_target(root)
            self.assertEqual(self.run_ps("install", target, old_package)[1]["decision"], "proceed")
            self.assertEqual(self.run_ps("uninstall", target, old_package)[1]["decision"], "proceed")
            from ufg_installer.core import Installer
            engine = Installer(package_root=new_package, process_checker=lambda: False)
            self.assertEqual(engine.install(target, "RE_ENABLE_UFG").decision, "abort")
            upgraded = engine.install(target, "UPGRADE_UFG_IN_PLACE")
            self.assertEqual(upgraded.decision, "proceed", upgraded.message)
            self.assertEqual((target / "dxcompiler.dll").read_bytes(), new_proxy)
            self.assertEqual((target / "AWOW Universal Female Generation" / "awow_ufg.dll").read_bytes(), new_payload)

    def test_python_disable_agp_replacement_powershell_matching_ufg_reenable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_package = self.make_package(root, package_name="old release")
            target = self.make_target(root)
            from ufg_installer.core import Installer
            old_engine = Installer(package_root=old_package, process_checker=lambda: False)
            self.assertEqual(old_engine.install(target).decision, "proceed")
            self.assertEqual(old_engine.uninstall(target).decision, "proceed")

            new_ck3, new_steam = b"fixture ck3 executable v2", b"fixture steam dxcompiler v2"
            new_agp_proxy, new_agp_payload = b"fixture compatible agp proxy v2", b"fixture compatible agp payload v2"
            new_proxy, new_payload = b"fixture ufg proxy v2", b"fixture ufg payload v2"
            new_package = self.make_package(
                root,
                package_name="new release",
                version="1.1.0",
                ck3=new_ck3,
                steam=new_steam,
                agp_proxy=new_agp_proxy,
                agp_payload=new_agp_payload,
                ufg_proxy=new_proxy,
                ufg_payload=new_payload,
            )
            (target / "ck3.exe").write_bytes(new_ck3)
            (target / "dxcompiler_original.dll").write_bytes(new_steam)
            (target / "dxcompiler.dll").write_bytes(new_agp_proxy)
            (target / "AGP Native Hook" / "agp_parenthook.dll").write_bytes(new_agp_payload)
            self.assertEqual(self.run_ps("install", target, new_package)[1]["decision"], "abort")
            code, result = self.run_ps("install", target, new_package, "RE_ENABLE_UFG")
            self.assertEqual((code, result["decision"]), (0, "proceed"), result)
            self.assertEqual((target / "dxcompiler.dll").read_bytes(), new_proxy)
            self.assertEqual((target / "AWOW Universal Female Generation" / "awow_ufg.dll").read_bytes(), new_payload)

    def test_powershell_new_installer_uninstalls_old_owned_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_package = self.make_package(root, package_name="old release")
            new_package = self.make_package(root, package_name="new release", version="1.1.0", ufg_proxy=b"fixture ufg proxy v2", ufg_payload=b"fixture ufg payload v2")
            target = self.make_target(root)
            from ufg_installer.core import Installer
            self.assertEqual(Installer(package_root=old_package, process_checker=lambda: False).install(target).decision, "proceed")
            old_proxy = (target / "dxcompiler.dll").read_bytes()
            code, result = self.run_ps("uninstall", target, new_package)
            self.assertEqual((code, result["decision"], result["next_state"]), (0, "proceed", "ufg_proxy_only"), result)
            self.assertEqual((target / "dxcompiler.dll").read_bytes(), old_proxy)
            self.assertEqual(Installer(package_root=new_package, process_checker=lambda: False).classify(target).state, "ufg_proxy_only")


if __name__ == "__main__":
    unittest.main()
