#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "ufg_generation.h"
#include "ufg_history.h"
#include "ufg_build_profile.h"
#include <string>
namespace ufg {
namespace {
DWORD WINAPI PatchThread(LPVOID) {
    HANDLE guard=CreateMutexW(nullptr,FALSE,L"Local\\AWOW_UFG_1_21_0_3_PATCHED");
    if (!guard) return 1;
    if (GetLastError()==ERROR_ALREADY_EXISTS) {CloseHandle(guard);Log("UFG: duplicate initialization skipped.");return 0;}
    try {
        if (!SelectAndValidateProfile()) return 1;
        wchar_t dependency_path[32768]{};std::string dependency_hash;
        auto dependency=GetModuleHandleW(L"agp_parenthook.dll");
        if (!dependency||!GetModuleFileNameW(dependency,dependency_path,32768)||!Sha256File(dependency_path,&dependency_hash)||_stricmp(dependency_hash.c_str(),Profile().agp_payload_sha256)) {
            Log("UFG: loaded AGP dependency identity mismatch; no UFG changes made.");return 1;
        }

        if (InspectAgpState()!=DependencyState::Patched) {Log("UFG: AGP readiness is incomplete; no UFG changes made.");return 1;}
        TextSection text{};GenerationPatchPlan generation{};HistoryPatchPlan history{};
        if (!GetTextSection(&text)||!PrepareGenerationPatch(text,&generation)||!PrepareHistoryPatch(text,&history)) return 1;
        BeginPatchTransaction();
        if (!ApplyHistoryPatch(history)||!ApplyGenerationPatch(generation)) {AbortPatchTransaction();Log("UFG: staging failed; no UFG game-code writes made.");return 1;}
        if (!CommitPatchTransaction()) return 1;
        Log("UFG v1.1.0: native patches committed. Gameplay acceptance is separate from preflight.");return 0;
    } catch (...) {AbortPatchTransaction();Log("UFG: preparation exception; no new UFG changes committed.");return 1;}
}
}
}
BOOL APIENTRY DllMain(HMODULE module,DWORD reason,LPVOID) {
    if (reason==DLL_PROCESS_ATTACH) {DisableThreadLibraryCalls(module);HANDLE thread=CreateThread(nullptr,0,ufg::PatchThread,nullptr,0,nullptr);if (thread) CloseHandle(thread);}return TRUE;
}
