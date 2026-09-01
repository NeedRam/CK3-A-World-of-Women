from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "Installer" / "python"))

from ufg_installer import gui
from ufg_installer.core import ConfirmationRequest, Result
from ufg_installer.discovery import SteamTarget, default_target, select_target, standard_steam_executable


class GuiPathTests(unittest.TestCase):
    def test_default_target_uses_first_discovered_executable(self) -> None:
        discovered = [SteamTarget(Path("C:/Steam One/.../binaries"), Path("C:/Steam One"), "registry")]
        self.assertEqual(default_target(discovered), Path("C:/Steam One/.../binaries/ck3.exe"))

    def test_default_target_falls_back_to_program_files_steam(self) -> None:
        with mock.patch.dict(os.environ, {"ProgramFiles(x86)": "C:/Program Files (x86)", "ProgramFiles": "C:/Program Files"}, clear=True):
            self.assertEqual(standard_steam_executable(), Path("C:/Program Files (x86)/Steam/steamapps/common/Crusader Kings III/binaries/ck3.exe"))

    def test_initial_target_uses_canonical_windows_capitalization(self) -> None:
        self.assertEqual(gui.normalize_display_path(r"c:\Steam\steamapps\common\Crusader Kings III\binaries\ck3.exe"), r"C:\Steam\steamapps\common\Crusader Kings III\binaries\ck3.exe")
        self.assertEqual(gui.normalize_display_path("relative/path/ck3.exe"), str(Path("relative/path/ck3.exe")))

    @unittest.skipUnless(os.name == "nt", "Windows filesystem capitalization test")
    def test_existing_default_path_uses_on_disk_capitalization(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / "Steam Library" / "steamapps" / "common" / "Crusader Kings III" / "binaries" / "ck3.exe"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"fixture")
            self.assertEqual(gui.normalize_display_path(str(executable).lower()), str(executable.resolve()))

    def test_result_message_uses_ufg_success_copy(self) -> None:
        self.assertEqual(gui._result_message(Result("install", "proceed", "agp_ready", "managed_ufg", message="detail")), "AWOW Universal Female Generation installed successfully.")
        self.assertEqual(gui._result_message(Result("uninstall", "proceed", "managed_ufg", "ufg_proxy_only", message="detail")), "UFG payload disabled; the active UFG proxy remains unchanged and continues loading AGP alone.")

    def test_result_message_preserves_non_success_detail(self) -> None:
        result = Result("install", "reject", "unknown_conflicting", "unknown_conflicting", message="safe refusal")
        self.assertEqual(gui._result_message(result), "install: reject\nsafe refusal")

    def test_confirmation_is_a_two_button_question_without_typing(self) -> None:
        request = ConfirmationRequest("managed_upgrade", "INTERNAL_TOKEN", "UFG is already installed", "Continue with the upgrade?")
        parent = mock.Mock()
        with mock.patch.object(gui.messagebox, "askokcancel", return_value=True) as ask:
            self.assertTrue(gui._ask_confirmation(request, parent))
        ask.assert_called_once_with(request.title, request.message, icon="question", default=gui.messagebox.CANCEL, parent=parent)

    def test_executable_selection_normalizes_to_binaries_directory(self) -> None:
        self.assertEqual(select_target("C:/Steam/steamapps/common/Crusader Kings III/binaries/ck3.exe"), Path("C:/Steam/steamapps/common/Crusader Kings III/binaries"))

    def test_browse_updates_only_for_ck3_executable(self) -> None:
        parent = mock.Mock()
        target_var = mock.Mock()
        target_var.get.return_value = "C:/Steam/steamapps/common/Crusader Kings III/binaries/ck3.exe"
        with mock.patch.object(gui.filedialog, "askopenfilename", return_value="D:/Games/Crusader Kings III/binaries/ck3.exe"):
            gui._browse_for_target(parent, target_var)
        target_var.set.assert_called_once_with(str(Path("D:/Games/Crusader Kings III/binaries/ck3.exe")))
        target_var.reset_mock()
        with mock.patch.object(gui.filedialog, "askopenfilename", return_value="D:/Games/other.exe"), mock.patch.object(gui.messagebox, "showerror") as showerror:
            gui._browse_for_target(parent, target_var)
        target_var.set.assert_not_called()
        showerror.assert_called_once()


if __name__ == "__main__":
    unittest.main()
