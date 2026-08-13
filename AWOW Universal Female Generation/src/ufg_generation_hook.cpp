#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include "ufg_generation.h"
#include "ufg_history.h"
#include "ufg_patch_runtime.h"

#include <string>

namespace ufg {
namespace {

constexpr char kTargetSha256[] = "2D00FF3101EF70B566F2FCBAE292F09263199C80E9DC8F139B82D7D96F83DB86";

bool VerifyExecutable() {
	wchar_t path[MAX_PATH]{};
	if (GetModuleFileNameW(nullptr, path, MAX_PATH) == 0) {
		return false;
	}
	std::string hash;
	return Sha256File(path, &hash) && hash == kTargetSha256;
}

bool ApplyPatch() {
	if (!VerifyExecutable()) {
		Log("UFG: unsupported ck3.exe; no changes made.");
		return false;
	}
	TextSection text{};
	if (!GetTextSection(&text)) {
		Log("UFG: unable to locate ck3.exe .text section; no changes made.");
		return false;
	}

	GenerationPatchPlan generation{};
	HistoryPatchPlan history{};
	const bool generation_ok = PrepareGenerationPatch(text, &generation);
	const bool history_ok = PrepareHistoryPatch(text, &history);
	if (!generation_ok || !history_ok) {
		return false;
	}

	const bool history_applied = ApplyHistoryPatch(history);
	const bool generation_applied = ApplyGenerationPatch(generation);
	if (!history_applied || !generation_applied) {
		Log("UFG: patch write failed; CK3 may be unchanged or partially patched. Exit without saving and report the log.");
		return false;
	}
	Log("UFG: enabled female history characters and eligible NPC generation with birth, save, player, player-dynasty, and Ruler Designer exclusions.");
	return true;
}

DWORD WINAPI PatchThread(LPVOID) {
	HANDLE mutex = CreateMutexW(nullptr, FALSE, L"Local\\AWOW_UFG_1_19_0_6_PATCHED");
	if (mutex == nullptr) {
		Log("UFG: unable to create the patch guard; no changes made.");
		return 1;
	}
	if (GetLastError() == ERROR_ALREADY_EXISTS) {
		Log("UFG: patches are already active; no duplicate writes performed.");
		CloseHandle(mutex);
		return 0;
	}
	ApplyPatch();
	return 0;
}

} // namespace
} // namespace ufg

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
	if (reason == DLL_PROCESS_ATTACH) {
		DisableThreadLibraryCalls(module);
		HANDLE thread = CreateThread(nullptr, 0, ufg::PatchThread, nullptr, 0, nullptr);
		if (thread != nullptr) {
			CloseHandle(thread);
		}
	}
	return TRUE;
}
