#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <algorithm>
#include <cstring>
#include <cstdlib>
#include "ufg_build_profile.h"
#include "ufg_profiles.generated.h"
namespace ufg {
namespace {
std::uint8_t* Base() { return reinterpret_cast<std::uint8_t*>(GetModuleHandleW(nullptr)); }
bool InText(const TextSection& text, const std::uint8_t* address, std::size_t size) {
    const auto a=reinterpret_cast<std::uintptr_t>(address), b=reinterpret_cast<std::uintptr_t>(text.begin);
    return a>=b && a-b<=text.size && size<=text.size-(a-b);
}
bool VerifySite(const NativeSite& site, const TextSection& text, std::uint8_t* base) {
    const auto bytes=ParseHex(site.original);auto* address=base+site.rva;
    if (bytes.empty() || !InText(text,address,bytes.size()) || std::memcmp(address,bytes.data(),bytes.size())) return false;
    const std::string mask(bytes.size(),'x');
    return FindPattern(text,{bytes.data(),mask.c_str(),bytes.size()}).size()==1;
}
}
const NativeProfile& Profile() { return kProfile; }
std::vector<std::uint8_t> ParseHex(const char* value) {
    std::vector<std::uint8_t> result;
    while (*value) { while (*value==' ') ++value;if (!*value) break;char* end=nullptr;
        auto item=std::strtoul(value,&end,16);if (end==value || item>255) return {};result.push_back(static_cast<std::uint8_t>(item));value=end;
    }return result;
}
const NativeSite* Site(const char* id) { for (const auto& site:kSites) if (!std::strcmp(id,site.id)) return &site;return nullptr; }
std::uint8_t* SiteAddress(const char* id) { const auto* site=Site(id);return site?Base()+site->rva:nullptr; }
bool ValidateProfileImage(const TextSection& text, std::uint8_t* base) {
    for (const auto& site:kSites) if (!VerifySite(site,text,base)) { Log(site.id);return false; }
    for (const auto& site:kValidation) if (!VerifySite(site,text,base)) { Log(site.id);return false; }
    for (const auto& call:kCalls) {
        auto* instruction=base+call.call_rva;std::int32_t delta{};auto bytes=ParseHex(call.prologue);
        if (!InText(text,instruction,5) || instruction[0]!=0xe8) return false;
        std::memcpy(&delta,instruction+1,4);auto* target=instruction+5+delta;
        if (target!=base+call.target_rva || !InText(text,target,bytes.size()) || std::memcmp(target,bytes.data(),bytes.size())) return false;
    }
    for (const auto& reference:kReferences) {
        auto bytes=ParseHex(reference.original);auto* instruction=base+reference.rva;std::int32_t delta{};
        if (!InText(text,instruction,bytes.size()) || std::memcmp(instruction,bytes.data(),bytes.size())) return false;
        std::memcpy(&delta,instruction+reference.displacement_offset,4);
        if (instruction+reference.instruction_size+delta!=base+reference.target_rva) return false;
    }
    return true;
}
bool SelectAndValidateProfile() {
    wchar_t path[32768]{};std::string digest;
    if (!GetModuleFileNameW(nullptr,path,32768) || !Sha256File(path,&digest) || _stricmp(digest.c_str(),Profile().executable_sha256)) {
        Log("UFG: unsupported executable identity; no UFG changes made.");return false;
    }
    Log(Profile().id);Log(Profile().executable_sha256);TextSection text{};
    if (!GetTextSection(&text) || !ValidateProfileImage(text,Base())) { Log("UFG: profile preflight failed; no UFG changes made.");return false; }
    return true;
}
bool IsSupportedOrigin(unsigned hook, std::uintptr_t origin) {
    // The legacy direct site belongs to manager save-record reconstruction,
    // not NPC creation. Its gender assignments must remain untouched.
    if (hook==0) return false;
    if (hook==1) return std::find(std::begin(kOrigins_template),std::end(kOrigins_template),origin)!=std::end(kOrigins_template);
    return false;
}
bool IsRulerDesignerWrapperOrigin(std::uintptr_t origin) {
    return std::find(std::begin(kOrigins_ruler_designer_wrapper),std::end(kOrigins_ruler_designer_wrapper),origin)!=std::end(kOrigins_ruler_designer_wrapper);
}
DependencyState InspectAgpSite(const AgpSite& site, const std::uint8_t* address) {
    const auto original=ParseHex(site.original);std::vector<std::uint8_t> actual(original.size());
    if (!ReadMemory(address,actual.data(),actual.size())) return DependencyState::Invalid;
    if (actual==original) return DependencyState::Original;
    if (site.patch_offset+site.overwrite>actual.size()) return DependencyState::Invalid;
    auto expected=original;
    if (!site.detour) {
        auto replacement=ParseHex(site.replacement);if (replacement.size()!=site.overwrite) return DependencyState::Invalid;
        std::copy(replacement.begin(),replacement.end(),expected.begin()+site.patch_offset);
    } else {
        const auto offset=site.patch_offset;
        if (site.overwrite<5 || actual[offset]!=0xe9) return DependencyState::Invalid;
        for (std::size_t i=5;i<site.overwrite;++i) if (actual[offset+i]!=0x90) return DependencyState::Invalid;
        std::int32_t delta{};std::memcpy(&delta,actual.data()+offset+1,4);
        auto* target=address+offset+5+delta;MEMORY_BASIC_INFORMATION memory{};
        if (!VirtualQuery(target,&memory,sizeof(memory)) || memory.State!=MEM_COMMIT || (memory.Protect&(PAGE_GUARD|PAGE_NOACCESS)) || !(memory.Protect&(PAGE_EXECUTE|PAGE_EXECUTE_READ|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY))) return DependencyState::Invalid;
        const auto prefix=ParseHex(site.relay_prefix);std::vector<std::uint8_t> relay(prefix.size());
        if (prefix.empty() || !ReadMemory(target,relay.data(),relay.size()) || relay!=prefix) return DependencyState::Invalid;
        std::copy(actual.begin()+offset,actual.begin()+offset+site.overwrite,expected.begin()+offset);
    }
    return actual==expected?DependencyState::Patched:DependencyState::Invalid;
}
DependencyState InspectAgpState() {
    std::size_t originals=0,patched=0;
    for (const auto& site:kAgpSites) {
        const auto state=InspectAgpSite(site,Base()+site.rva);
        if (state==DependencyState::Invalid) return state;
        if (state==DependencyState::Original) ++originals;else ++patched;
    }
    return !originals?DependencyState::Patched:!patched?DependencyState::Original:DependencyState::Partial;
}
}
