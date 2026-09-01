from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "Installer"


class ContractFileTests(unittest.TestCase):
    def validate_pair(self, document: str, schema: str) -> None:
        data = json.loads((CONTRACT / document).read_text(encoding="utf-8"))
        contract = json.loads((CONTRACT / schema).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(contract)
        Draft202012Validator(contract).validate(data)

    def test_release_manifest(self) -> None:
        self.validate_pair("release-manifest.json", "spec/release-manifest.schema.json")

    def test_scenario_fixtures(self) -> None:
        self.validate_pair("fixtures/scenarios.json", "spec/scenario-fixtures.schema.json")

    def test_compatibility_evidence(self) -> None:
        self.validate_pair("fixtures/compatibility-evidence.json", "spec/compatibility-evidence.schema.json")

    def test_transition_and_package_contracts_are_valid_json(self) -> None:
        for path in (CONTRACT / "spec" / "state-transitions.json", CONTRACT / "spec" / "package-layout.json"):
            self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)

    def test_manifest_declares_exact_agp_hash_dependency(self) -> None:
        manifest = json.loads((CONTRACT / "release-manifest.json").read_text(encoding="utf-8"))
        candidates = manifest["compatible_agp_builds"]
        self.assertTrue(candidates)
        for candidate in candidates:
            for key in ("executable_sha256", "proxy_sha256", "payload_sha256", "original_dxcompiler_sha256"):
                self.assertRegex(candidate[key], r"^[0-9a-f]{64}$")
        self.assertIn("managed_ufg", {seed["state"] for seed in manifest["compatibility"]["seeds"]})
        self.assertIn("ufg_proxy_only", {seed["state"] for seed in manifest["compatibility"]["seeds"]})

    def test_package_entrypoints_are_top_level_in_layout(self) -> None:
        layout = json.loads((CONTRACT / "spec" / "package-layout.json").read_text(encoding="utf-8"))
        paths = {item["relative_path"] for item in layout["root_entries"]}
        self.assertTrue({"UFG-Installer.exe", "UFG-Uninstaller.exe", "Install UFG.bat", "Uninstall UFG.bat", "PRIVACY.md", "SECURITY.md", "SIGNING.md", "BUILD_TOOLCHAIN.json"}.issubset(paths))
        self.assertFalse(any(path.startswith("Installer/UFG") for path in paths))

    def test_batch_launchers_do_not_end_quoted_package_root_with_backslash(self) -> None:
        for name in ("Install UFG.bat", "Uninstall UFG.bat"):
            launcher = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn('-PackageRoot "%~dp0."', launcher)
            self.assertNotIn('-PackageRoot "%~dp0"', launcher)

    def test_release_workflow_validates_tag_against_checked_in_manifest(self) -> None:
        workflow = (ROOT.parent / ".github" / "workflows" / "ufg-release.yml").read_text(encoding="utf-8")
        self.assertIn("GITHUB_REF_NAME", workflow)
        self.assertIn("refs/tags/ufg-v", workflow)
        self.assertIn("manifest.release.version", workflow)
        self.assertIn("does not match checked-in manifest version", workflow)
        self.assertIn("steps.release.outputs.version", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("merge-base --is-ancestor HEAD origin/main", workflow)
        self.assertIn("actions/attest@v4", workflow)
        self.assertIn("attestations: write", workflow)
        self.assertNotIn("github.event.inputs.version || '1.0.0'", workflow)

    def test_native_toolchain_and_version_metadata_are_declared(self) -> None:
        toolchain = json.loads((ROOT / "toolchain.json").read_text(encoding="utf-8"))
        self.assertEqual(toolchain["visual_studio_version_range"], "[17.0,18.0)")
        self.assertEqual(toolchain["vc_tools_version"], "14.44.35207")
        self.assertEqual(toolchain["windows_sdk_version"], "10.0.22621.0")
        self.assertEqual((toolchain["host_architecture"], toolchain["target_architecture"], toolchain["vcvars_architecture"]), ("x64", "x64", "amd64"))
        build_script = (ROOT / "build.ps1").read_text(encoding="utf-8")
        self.assertIn("-vcvars_ver=", build_script)
        self.assertIn("Expected VCToolsVersion", build_script)
        self.assertIn("Expected WindowsSDKVersion", build_script)
        version_resource = (ROOT / "version.rc").read_text(encoding="utf-8")
        self.assertIn('VALUE "OriginalFilename", UFG_ORIGINAL_FILENAME', version_resource)
        self.assertIn('VALUE "ProductVersion", "1.0.0.0', version_resource)

    def test_release_builder_excludes_development_content_and_packages_policies(self) -> None:
        builder = (ROOT / "release" / "build-release.ps1").read_text(encoding="utf-8")
        for policy in ("PRIVACY.md", "SECURITY.md", "SIGNING.md"):
            self.assertIn(policy, builder)
            self.assertTrue((ROOT / policy).is_file())
        for excluded in ("tests", "fixtures", "build.py", "requirements-build.txt"):
            self.assertIn(excluded, builder)

    def test_end_user_upgrade_handoff_documents_agp_v101_confirmation(self) -> None:
        readme = (ROOT / "release" / "END_USER_README.md").read_text(encoding="utf-8")
        self.assertIn("I_UNDERSTAND_UNKNOWN_CONFLICT", readme)
        self.assertIn("AGP v1.0.1 predates this UFG v1.0.0 proxy hash", readme)
        for ufg_token in ("UPGRADE_UFG_IN_PLACE", "ADOPT_UFG_LAYOUT", "RE_ENABLE_UFG"):
            self.assertNotIn(ufg_token, readme)

    def test_interactive_ufg_frontends_use_two_button_confirmations(self) -> None:
        gui = (ROOT / "Installer" / "python" / "ufg_installer" / "gui.py").read_text(encoding="utf-8")
        powershell = (ROOT / "Installer" / "powershell" / "engine.ps1").read_text(encoding="utf-8")
        self.assertIn("askokcancel", gui)
        self.assertNotIn("askstring", gui)
        self.assertNotIn("simpledialog", gui)
        self.assertIn("MessageBoxButtons]::OKCancel", powershell)
        self.assertIn("MessageBoxDefaultButton]::Button2", powershell)
        self.assertNotIn("Read-Host", powershell)

    def test_powershell_engine_hashing_does_not_depend_on_module_autoloading(self) -> None:
        powershell = (ROOT / "Installer" / "powershell" / "engine.ps1").read_text(encoding="utf-8")
        self.assertIn("[Security.Cryptography.SHA256]::Create()", powershell)
        self.assertNotIn("Get-FileHash", powershell)


if __name__ == "__main__":
    unittest.main()
