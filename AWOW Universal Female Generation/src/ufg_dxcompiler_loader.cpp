#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstring>
#include "ufg_build_profile.h"
namespace {
HMODULE g_loader_module=nullptr;
INIT_ONCE g_dxcompiler_init=INIT_ONCE_STATIC_INIT;
using DxcCreateInstance_t=HRESULT(WINAPI*)(REFCLSID,REFIID,LPVOID*);
using DxcCreateInstance2_t=HRESULT(WINAPI*)(void*,REFCLSID,REFIID,LPVOID*);
DxcCreateInstance_t g_DxcCreateInstance=nullptr;
DxcCreateInstance2_t g_DxcCreateInstance2=nullptr;
void Log(const char* message) {
    auto path=ufg::ExecutableDirectory()+L"awow_ufg_dxcompiler_loader.log";
    HANDLE file=CreateFileW(path.c_str(),FILE_APPEND_DATA,FILE_SHARE_READ,nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return;DWORD count=0;
    WriteFile(file,message,static_cast<DWORD>(std::strlen(message)),&count,nullptr);WriteFile(file,"\r\n",2,&count,nullptr);CloseHandle(file);
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

bool ExactHash(const std::wstring& path,const char* expected) {std::string digest;return ufg::Sha256File(path.c_str(),&digest)&&!_stricmp(digest.c_str(),expected);}
DWORD WINAPI LoadPayloadThread(LPVOID) {
    if (!EnsureRealDxcompiler()) return 1;
    const auto directory=ufg::ExecutableDirectory();const auto& profile=ufg::Profile();
    const bool compatible=ufg::SelectAndValidateProfile()&&
        ExactHash(directory+L"AGP Native Hook\\agp_parenthook.dll",profile.agp_payload_sha256)&&
        ExactHash(directory+L"dxcompiler_original.dll",profile.original_dxcompiler_sha256);
    if (!LoadLibraryW((directory+L"AGP Native Hook\\agp_parenthook.dll").c_str())) {Log("UFG loader: AGP payload missing; UFG skipped.");return 1;}
    if (!compatible) {Log("UFG loader: unsupported CK3/AGP dependency; UFG skipped. AGP initialization was still attempted.");return 1;}
    const auto deadline=GetTickCount64()+15000;
    auto state=ufg::DependencyState::Original;
    do {state=ufg::InspectAgpState();if (state==ufg::DependencyState::Patched) break;Sleep(25);} while(GetTickCount64()<deadline);
    if (state!=ufg::DependencyState::Patched) {Log("UFG loader: AGP readiness incomplete or timed out; no UFG payload loaded.");return 1;}
    Log("UFG loader: all 22 AGP patch sites verified, including parent serialization.");
    if (GetFileAttributesW((directory+L"AWOW Universal Female Generation\\awow_ufg.dll").c_str())==INVALID_FILE_ATTRIBUTES) {Log("UFG loader: UFG payload absent; AGP remains active alone.");return 0;}
    if (!LoadLibraryW((directory+L"AWOW Universal Female Generation\\awow_ufg.dll").c_str())) {Log("UFG loader: UFG payload failed to load; AGP remains active.");return 1;}
    Log("UFG loader: UFG payload loaded after AGP readiness verification.");return 0;
}
}
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
