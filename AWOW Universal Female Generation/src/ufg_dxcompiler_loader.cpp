#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include "ufg_patch_runtime.h"

#include <array>
#include <cstdint>
#include <cstring>
#include <cwchar>
#include <string>
#include <vector>

namespace {

constexpr char kTargetSha256[] = "2D00FF3101EF70B566F2FCBAE292F09263199C80E9DC8F139B82D7D96F83DB86";
constexpr DWORD kAgpTimeoutMilliseconds = 15000;

HMODULE g_loader_module = nullptr;
INIT_ONCE g_dxcompiler_init = INIT_ONCE_STATIC_INIT;

using DxcCreateInstance_t = HRESULT(WINAPI*)(REFCLSID, REFIID, LPVOID*);
using DxcCreateInstance2_t = HRESULT(WINAPI*)(void*, REFCLSID, REFIID, LPVOID*);
DxcCreateInstance_t g_DxcCreateInstance = nullptr;
DxcCreateInstance2_t g_DxcCreateInstance2 = nullptr;

enum class AgpPatchShape {
	ShortJumpAt7,
	NearJumpAt7,
	NearJumpAt8,
	NopsAt7,
	DetourAt0,
	CloseFamilyDetour,
	HistoryNearJump
};

struct AgpPatchSite {
	const char* name{};
	ufg::Pattern original{};
	std::size_t expected_count{};
	AgpPatchShape shape{};
	std::vector<std::uint8_t*> addresses;
};

#define UFG_PATTERN(name, mask_value, ...) \
	static const std::uint8_t name##_bytes[] = { __VA_ARGS__ }; \
	static const char name##_mask[] = mask_value; \
	static const ufg::Pattern name{ name##_bytes, name##_mask, sizeof(name##_bytes) }

UFG_PATTERN(agp_history,
	"xxxxxxxxx????xxxx",
	0x44,0x38,0xA7,0x99,0x01,0x00,0x00,0x0F,0x84,0,0,0,0,0x49,0x8B,0x4E,0x10);
UFG_PATTERN(agp_close_family,
	"xxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
	0x80,0xB9,0x99,0x01,0x00,0x00,0x00,0x4C,0x8B,0xC9,0x74,0x3D,0x4C,0x3B,0xC1,0x74,0x35,0x49,0x8B,0x88,0xA0,0x01,0x00,0x00,0xB8,0xFF,0xFF,0xFF,0xFF);
UFG_PATTERN(agp_parent_roles,
	"xxxxxxxxxxxxxxxx????xxx????xxxx",
	0x80,0xBE,0x99,0x01,0x00,0x00,0x00,0x48,0x8B,0xD6,0x48,0x8B,0xCB,0x74,0x07,0xE8,0,0,0,0,0xEB,0x05,0xE8,0,0,0,0,0x48,0x83,0xC7,0x04);
UFG_PATTERN(agp_father_runtime_rdi,
	"xxxxxxxx?xxx????xxxxxxxxxxxxxxx",
	0x80,0xBF,0x99,0x01,0x00,0x00,0x00,0x74,0,0x4C,0x8D,0x05,0,0,0,0,0xC7,0x85,0x30,0x01,0x00,0x00,0,0,0,0,0xBA,0x00,0x02,0x00,0x00);
UFG_PATTERN(agp_father_runtime_rsi,
	"xxxxxxxx?xxx????xxxxxxxxxxxxxxx",
	0x80,0xBE,0x99,0x01,0x00,0x00,0x00,0x74,0,0x4C,0x8D,0x05,0,0,0,0,0xC7,0x85,0x30,0x01,0x00,0x00,0,0,0,0,0xBA,0x00,0x02,0x00,0x00);
UFG_PATTERN(agp_father_pregnancy_a,
	"xxxxxxxxxx????xxxxxxxxx",
	0x41,0x80,0xBE,0x99,0x01,0x00,0x00,0x00,0x0F,0x84,0,0,0,0,0x48,0x8D,0x54,0x24,0x40,0x49,0x8B,0xCE,0xE8);
UFG_PATTERN(agp_father_pregnancy_b,
	"xxxxxxxxx????xxxxxxxxx",
	0x80,0xBE,0x99,0x01,0x00,0x00,0x00,0x0F,0x84,0,0,0,0,0x48,0x8D,0x54,0x24,0x40,0x48,0x8B,0xCE,0xE8);
UFG_PATTERN(agp_father_validation,
	"xxxxxxxxx????xxxxx????xxx",
	0x80,0xBE,0x99,0x01,0x00,0x00,0x00,0x0F,0x85,0,0,0,0,0x48,0x3B,0xF3,0x0F,0x84,0,0,0,0,0x48,0x8B,0x05);
UFG_PATTERN(agp_father_persistence,
	"xxxxxxxxxxxxx",
	0x8B,0x46,0x18,0x89,0x42,0x04,0x48,0x8B,0x87,0xB8,0x01,0x00,0x00);
UFG_PATTERN(agp_mother_runtime_rdi,
	"xxxxxxxx?xxx????xxxxxxxxxxxxxxx",
	0x80,0xBF,0x99,0x01,0x00,0x00,0x01,0x74,0,0x4C,0x8D,0x05,0,0,0,0,0xC7,0x85,0x30,0x01,0x00,0x00,0,0,0,0,0xBA,0x00,0x02,0x00,0x00);
UFG_PATTERN(agp_mother_runtime_rsi,
	"xxxxxxxx?xxx????xxxxxxxxxxxxxxx",
	0x80,0xBE,0x99,0x01,0x00,0x00,0x01,0x74,0,0x4C,0x8D,0x05,0,0,0,0,0xC7,0x85,0x30,0x01,0x00,0x00,0,0,0,0,0xBA,0x00,0x02,0x00,0x00);
UFG_PATTERN(agp_mother_pregnancy,
	"xxxxxxxxx????xxxxxxxxx",
	0x80,0xBB,0x99,0x01,0x00,0x00,0x00,0x0F,0x85,0,0,0,0,0x48,0x8D,0x54,0x24,0x40,0x48,0x8B,0xCB,0xE8);
UFG_PATTERN(agp_mother_validation,
	"xxxxxxxxx????xxxxx????xxx",
	0x80,0xBE,0x99,0x01,0x00,0x00,0x00,0x0F,0x84,0,0,0,0,0x48,0x3B,0xF3,0x0F,0x84,0,0,0,0,0x48,0x8B,0x05);
UFG_PATTERN(agp_mother_persistence,
	"xxxxxxxxxxxx",
	0x8B,0x46,0x18,0x89,0x02,0x48,0x8B,0x87,0xB8,0x01,0x00,0x00);

#undef UFG_PATTERN

void Log(const char* message) {
	char path[MAX_PATH]{};
	if (GetModuleFileNameA(g_loader_module, path, MAX_PATH) == 0) return;
	char* separator = std::strrchr(path, '\\');
	if (separator == nullptr) return;
	std::strcpy(separator + 1, "awow_ufg_dxcompiler_loader.log");
	HANDLE file = CreateFileA(path, FILE_APPEND_DATA, FILE_SHARE_READ, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
	if (file == INVALID_HANDLE_VALUE) return;
	DWORD written = 0;
	WriteFile(file, message, static_cast<DWORD>(std::strlen(message)), &written, nullptr);
	WriteFile(file, "\r\n", 2, &written, nullptr);
	CloseHandle(file);
}

std::vector<AgpPatchSite> BuildAgpSites() {
	return {
		{ "history validation", agp_history, 1, AgpPatchShape::HistoryNearJump },
		{ "close-family helper", agp_close_family, 1, AgpPatchShape::CloseFamilyDetour },
		{ "parent-role reconstruction", agp_parent_roles, 1, AgpPatchShape::DetourAt0 },
		{ "female-father runtime RDI", agp_father_runtime_rdi, 1, AgpPatchShape::ShortJumpAt7 },
		{ "female-father runtime RSI", agp_father_runtime_rsi, 1, AgpPatchShape::ShortJumpAt7 },
		{ "female-father pregnancy A", agp_father_pregnancy_a, 1, AgpPatchShape::NearJumpAt8 },
		{ "female-father pregnancy B", agp_father_pregnancy_b, 1, AgpPatchShape::NearJumpAt7 },
		{ "female-father validation", agp_father_validation, 1, AgpPatchShape::NopsAt7 },
		{ "female-father persistence", agp_father_persistence, 1, AgpPatchShape::DetourAt0 },
		{ "male-mother runtime RDI", agp_mother_runtime_rdi, 1, AgpPatchShape::ShortJumpAt7 },
		{ "male-mother runtime RSI", agp_mother_runtime_rsi, 1, AgpPatchShape::ShortJumpAt7 },
		{ "male-mother pregnancy", agp_mother_pregnancy, 2, AgpPatchShape::NearJumpAt7 },
		{ "male-mother validation", agp_mother_validation, 1, AgpPatchShape::NopsAt7 },
		{ "male-mother persistence", agp_mother_persistence, 1, AgpPatchShape::DetourAt0 }
	};
}

bool IsNearJump(const std::uint8_t* address) {
	return address[0] == 0xE9 && address[5] == 0x90;
}

bool IsPatched(const AgpPatchSite& site, const std::uint8_t* address) {
	switch (site.shape) {
	case AgpPatchShape::ShortJumpAt7: return address[7] == 0xEB;
	case AgpPatchShape::NearJumpAt7: return IsNearJump(address + 7);
	case AgpPatchShape::NearJumpAt8: return IsNearJump(address + 8);
	case AgpPatchShape::NopsAt7:
		for (std::size_t index = 7; index < 13; ++index) if (address[index] != 0x90) return false;
		return true;
	case AgpPatchShape::DetourAt0: return address[0] == 0xE9;
	case AgpPatchShape::CloseFamilyDetour: return address[0] == 0xE9 && address[5] == 0x90 && address[6] == 0x90;
	case AgpPatchShape::HistoryNearJump: return IsNearJump(address + 7);
	}
	return false;
}

bool CaptureAgpSites(const ufg::TextSection& text, std::vector<AgpPatchSite>* sites) {
	for (auto& site : *sites) {
		site.addresses = ufg::FindPattern(text, site.original);
		if (site.addresses.size() != site.expected_count) {
			Log("UFG DXCompiler Loader: AGP signature mismatch; UFG will not load.");
			return false;
		}
	}
	return true;
}

enum class AgpState { Original, Patched, Partial };

AgpState InspectAgpState(const std::vector<AgpPatchSite>& sites, std::size_t* patched_count) {
	std::size_t patched = 0;
	std::size_t original = 0;
	std::size_t total = 0;
	for (const auto& site : sites) {
		for (const auto* address : site.addresses) {
			++total;
			if (IsPatched(site, address)) ++patched;
			else if (ufg::Matches(address, site.original)) ++original;
		}
	}
	if (patched_count != nullptr) *patched_count = patched;
	if (patched == total) return AgpState::Patched;
	if (original == total) return AgpState::Original;
	return AgpState::Partial;
}

BOOL CALLBACK InitializeRealDxcompiler(PINIT_ONCE, PVOID, PVOID*) {
	auto path = ufg::ExecutableDirectory();
	if (path.empty()) return FALSE;
	path += L"dxcompiler_original.dll";
	HMODULE original = LoadLibraryW(path.c_str());
	if (original == nullptr) {
		Log("UFG DXCompiler Loader: original dxcompiler_original.dll failed to load.");
		return FALSE;
	}
	g_DxcCreateInstance = reinterpret_cast<DxcCreateInstance_t>(GetProcAddress(original, "DxcCreateInstance"));
	g_DxcCreateInstance2 = reinterpret_cast<DxcCreateInstance2_t>(GetProcAddress(original, "DxcCreateInstance2"));
	if (g_DxcCreateInstance == nullptr || g_DxcCreateInstance2 == nullptr) {
		Log("UFG DXCompiler Loader: original exports were incomplete.");
		return FALSE;
	}
	return TRUE;
}

bool EnsureRealDxcompiler() {
	return InitOnceExecuteOnce(&g_dxcompiler_init, InitializeRealDxcompiler, nullptr, nullptr) != FALSE;
}

bool VerifyTargetExecutable() {
	wchar_t executable[MAX_PATH]{};
	if (GetModuleFileNameW(nullptr, executable, MAX_PATH) == 0) return false;
	std::string hash;
	if (!ufg::Sha256File(executable, &hash)) {
		Log("UFG DXCompiler Loader: unable to hash the running executable; UFG will not load.");
		return false;
	}
	if (hash != kTargetSha256) {
		Log("UFG DXCompiler Loader: unsupported ck3.exe; AGP will still be attempted, UFG will not load.");
		return false;
	}
	return true;
}

DWORD WINAPI LoadPayloadThread(LPVOID) {
	if (!EnsureRealDxcompiler()) {
		Log("UFG DXCompiler Loader: original DXCompiler could not be initialized; AGP and UFG will not be loaded.");
		return 1;
	}
	const bool target_supported = VerifyTargetExecutable();

	ufg::TextSection text{};
	auto sites = BuildAgpSites();
	const bool signatures_ready = target_supported && ufg::GetTextSection(&text) && CaptureAgpSites(text, &sites);

	auto directory = ufg::ExecutableDirectory();
	if (directory.empty()) return 1;
	const auto agp_path = directory + L"AGP Native Hook\\agp_parenthook.dll";
	HMODULE agp = LoadLibraryW(agp_path.c_str());
	if (agp == nullptr) {
		Log("UFG DXCompiler Loader: AGP payload failed to load; UFG skipped.");
		return 1;
	}
	Log("UFG DXCompiler Loader: AGP payload loaded.");
	if (!signatures_ready) {
		Log("UFG DXCompiler Loader: UFG preflight failed; UFG skipped.");
		return 1;
	}

	const ULONGLONG deadline = GetTickCount64() + kAgpTimeoutMilliseconds;
	AgpState state = AgpState::Original;
	do {
		state = InspectAgpState(sites, nullptr);
		if (state == AgpState::Patched) break;
		Sleep(25);
	} while (GetTickCount64() < deadline);

	if (state == AgpState::Original) {
		Log("UFG DXCompiler Loader: AGP patch timeout; UFG skipped.");
		return 1;
	}
	if (state == AgpState::Partial) {
		Log("UFG DXCompiler Loader: AGP is only partially patched. Exit CK3 without saving and report the log.");
		return 2;
	}

	const auto ufg_path = directory + L"AWOW Universal Female Generation\\awow_ufg.dll";
	if (LoadLibraryW(ufg_path.c_str()) == nullptr) {
		Log("UFG DXCompiler Loader: UFG payload failed to load; AGP remains active.");
		return 1;
	}
	Log("UFG DXCompiler Loader: UFG payload loaded after AGP verification.");
	return 0;
}

} // namespace

extern "C" __declspec(dllexport) HRESULT WINAPI DxcCreateInstance(REFCLSID class_id, REFIID interface_id, LPVOID* result) {
	if (!EnsureRealDxcompiler() || g_DxcCreateInstance == nullptr) return E_FAIL;
	return g_DxcCreateInstance(class_id, interface_id, result);
}

extern "C" __declspec(dllexport) HRESULT WINAPI DxcCreateInstance2(void* allocator, REFCLSID class_id, REFIID interface_id, LPVOID* result) {
	if (!EnsureRealDxcompiler() || g_DxcCreateInstance2 == nullptr) return E_FAIL;
	return g_DxcCreateInstance2(allocator, class_id, interface_id, result);
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
	if (reason == DLL_PROCESS_ATTACH) {
		g_loader_module = module;
		DisableThreadLibraryCalls(module);
		HANDLE thread = CreateThread(nullptr, 0, LoadPayloadThread, nullptr, 0, nullptr);
		if (thread != nullptr) {
			CloseHandle(thread);
		}
	}
	return TRUE;
}
