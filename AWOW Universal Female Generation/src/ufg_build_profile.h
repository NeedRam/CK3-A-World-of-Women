#pragma once
#include "ufg_patch_runtime.h"
namespace ufg {
struct NativeSite { const char* id; std::uintptr_t rva; const char* original; std::size_t overwrite; std::uintptr_t resume; };
struct NativeCall { const char* id; std::uintptr_t call_rva, target_rva; const char* prologue; };
struct NativeReference { const char* id; std::uintptr_t rva; const char* original; std::size_t displacement_offset, instruction_size; std::uintptr_t target_rva; };
struct AgpSite { const char* id; std::uintptr_t rva; const char* original; std::size_t patch_offset, overwrite; const char* replacement; const char* relay_prefix; int detour; };
struct CharacterOffsets {
    std::size_t character_id, gender, gender_lock, character_house, house_id, house_dynasty, game_state, players, player_count, request_house, database_slots, database_count, slot_stride, slot_object;
};
struct NativeProfile {
    const char* id; const char* version; const char* executable_sha256; const char* original_dxcompiler_sha256;
    const char* agp_version; const char* agp_proxy_sha256; const char* agp_payload_sha256;
    CharacterOffsets offsets;
    struct { std::uintptr_t game_root, characters, houses; } globals;
};
enum class DependencyState { Original, Patched, Partial, Invalid };
const NativeProfile& Profile();
bool SelectAndValidateProfile();
bool ValidateProfileImage(const TextSection& text, std::uint8_t* base);
const NativeSite* Site(const char* id);
std::uint8_t* SiteAddress(const char* id);
bool IsSupportedOrigin(unsigned hook, std::uintptr_t origin_rva);
bool IsRulerDesignerWrapperOrigin(std::uintptr_t origin_rva);
DependencyState InspectAgpSite(const AgpSite& site, const std::uint8_t* address);
DependencyState InspectAgpState();
std::vector<std::uint8_t> ParseHex(const char* value);
}
