#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <atomic>
#include <cstdio>
#include "ufg_generation.h"
#include "ufg_build_profile.h"
#include "ufg_relay.h"
namespace ufg {
namespace {
constexpr std::uint32_t kInvalid=0xffffffffU;
template<class T> bool Read(const void* pointer,std::size_t offset,T* out) {return pointer&&ReadMemory(static_cast<const std::uint8_t*>(pointer)+offset,out,sizeof(T));}
const void* Lookup(const std::uint8_t* base,std::uintptr_t global,std::uint32_t id,std::size_t id_offset,bool* valid) {
    if (id==kInvalid) return nullptr;
    const void* database=nullptr;std::uint32_t count=0;const std::uint8_t* slots=nullptr;
    const auto& o=Profile().offsets;
    if (!Read(base,global,&database)||!database||!Read(database,o.database_count,&count)||!Read(database,o.database_slots,&slots)||!slots||(id&0xffffffU)>=count) {*valid=false;return nullptr;}
    const void* object=nullptr;std::uint32_t actual=kInvalid;
    if (!Read(slots,static_cast<std::size_t>(id&0xffffffU)*o.slot_stride+o.slot_object,&object)||!object||!Read(object,id_offset,&actual)||actual!=id) {*valid=false;return nullptr;}
    return object;
}
std::uint32_t Dynasty(const std::uint8_t* base,std::uint32_t house_id,bool* valid) {
    const auto* house=Lookup(base,Profile().globals.houses,house_id,Profile().offsets.house_id,valid);
    std::uint32_t dynasty=kInvalid;if (house&&!Read(house,Profile().offsets.house_dynasty,&dynasty)) *valid=false;return dynasty;
}
}
std::uint8_t ResolveGenderForImage(const void* character,std::uint8_t requested,unsigned hook,std::uintptr_t origin,const void* request,const std::uint8_t* base,bool* unavailable,std::uintptr_t wrapper_origin) {
    if (unavailable) *unavailable=false;
    if (!character||!base||!IsSupportedOrigin(hook,origin)) return requested;
    // PORTING REGRESSION: retain the nested-caller exclusion from UFG 1.19.0.6.
    // Designer creation reaches the common wrapper before joining the player
    // roster or designer-character list, so those lookups cannot protect it.
    // Re-audit the Designer -> wrapper -> constructor chain and relay stack
    // offsets on every CK3 update; excluding only the direct caller is not enough.
    // See README.md, "Ruler Designer porting requirement", and the native tests.
    if (hook==1&&origin==0x2de53f1&&IsRulerDesignerWrapperOrigin(wrapper_origin)) return requested;
    const auto& o=Profile().offsets;const void* root=nullptr;const void* state=nullptr;const std::uint32_t* players=nullptr;std::int32_t count=0;
    auto unknown=[&]() {if (unavailable) *unavailable=true;return requested;};
    if (!Read(base,Profile().globals.game_root,&root)||!root||!Read(root,o.game_state,&state)||!state||!Read(state,o.player_count,&count)||count<0||count>64) return unknown();
    // A valid empty roster is ordinary pre-player generation, not failed lookup.
    if (!count) return 1;
    if (!Read(state,o.players,&players)||!players) return unknown();
    std::uint32_t id=kInvalid,house=kInvalid,requested_house=kInvalid;
    if (!Read(character,o.character_id,&id)||id==kInvalid||!Read(character,o.character_house,&house)) return unknown();
    if (hook==1&&(!request||!Read(request,o.request_house,&requested_house))) return unknown();
    bool valid=true;const auto dynasty=Dynasty(base,house,&valid);const auto requested_dynasty=Dynasty(base,requested_house,&valid);
    if (!valid) return unknown();
    for (std::int32_t i=0;i<count;++i) {
        std::uint32_t player=kInvalid;if (!Read(players,static_cast<std::size_t>(i)*4,&player)) return unknown();
        if (player==id) return requested;
        const auto* object=Lookup(base,Profile().globals.characters,player,o.character_id,&valid);
        std::uint32_t player_house=kInvalid;if (!object||!valid||!Read(object,o.character_house,&player_house)) return unknown();
        const auto player_dynasty=Dynasty(base,player_house,&valid);if (!valid) return unknown();
        if (player_dynasty!=kInvalid&&(player_dynasty==dynasty||player_dynasty==requested_dynasty)) return requested;
    }
    return 1;
}
extern "C" void __fastcall ResolveRuntimeGender(void* character,std::uint8_t requested,unsigned hook,std::uintptr_t origin,const void* request,const void* wrapper_return_slot) {
    if (!character) return;
    auto* base=reinterpret_cast<std::uint8_t*>(GetModuleHandleW(nullptr));bool unavailable=false;
    const auto origin_rva=origin-reinterpret_cast<std::uintptr_t>(base);
    std::uintptr_t wrapper_origin=0;
    const bool wrapper_readable=hook!=1||origin_rva!=0x2de53f1||ReadMemory(wrapper_return_slot,&wrapper_origin,sizeof(wrapper_origin));
    const auto wrapper_rva=wrapper_origin?wrapper_origin-reinterpret_cast<std::uintptr_t>(base):0;
    const auto gender=wrapper_readable?ResolveGenderForImage(character,requested,hook,origin_rva,request,base,&unavailable,wrapper_rva):requested;
    if (!wrapper_readable) unavailable=true;
    if (unavailable) {static std::atomic_flag reported=ATOMIC_FLAG_INIT;if (!reported.test_and_set()) Log("UFG: player protection lookup unavailable; requested gender preserved.");}
    unsigned bucket=5;
    if (hook==0&&origin_rva==0x2ddbbc8) bucket=0;
    else if (hook==0&&origin_rva==0x2ddbbf3) bucket=1;
    else if (hook==1&&origin_rva==0x2de53f1) bucket=2;
    else if (hook==1&&origin_rva==0x2f13033) bucket=3;
    else if (hook==1&&origin_rva==0x32cbad2) bucket=4;
    if (hook==1&&origin_rva==0x2de53f1&&IsRulerDesignerWrapperOrigin(wrapper_rva)) bucket=6;
    static std::atomic<unsigned> samples[7]{};
    if (samples[bucket].fetch_add(1)<3) {
        char message[224]{};
        std::snprintf(message,sizeof(message),"UFG_GENERATION origin=0x%llx hook=%u requested=%u resolved=%u character_id=%u protection_unavailable=%u wrapper_origin=0x%llx",static_cast<unsigned long long>(origin_rva),hook,requested,gender,ReadAt<std::uint32_t>(character,Profile().offsets.character_id),unavailable?1:0,static_cast<unsigned long long>(wrapper_rva));
        Log(message);
    }
    std::memcpy(static_cast<std::uint8_t*>(character)+Profile().offsets.gender,&gender,1);
}
std::vector<std::uint8_t> BuildGenerationRelay(unsigned hook,std::uint8_t* relay,const void* resume,const void* callback) {
    if (hook>1) return {};
    RelayCode code;
    // Replay the original load so RAX has exactly the original instruction result.
    if (!hook) code.Emit({0x41,0x0f,0xb6,0x46,0x08});else code.Emit({0x0f,0xb6,0x86,0xb4,0,0,0});
    code.Emit({0x9c,0x50,0x51,0x52,0x41,0x50,0x41,0x51,0x41,0x52,0x41,0x53,0x48,0x81,0xec,0x90,0,0,0});
    // 32-byte shadow space, fifth/sixth arguments, and six volatile XMM saves.
    for (unsigned i=0;i<6;++i) {code.Emit({0xf3,0x0f,0x7f,static_cast<std::uint8_t>(0x84+(i<<3)),0x24});code.Value<std::uint32_t>(0x30+i*16);}
    if (hook) code.Emit({0x48,0x8b,0xcb});
    if (!hook) code.Emit({0x41,0x0f,0xb6,0x56,0x08});else code.Emit({0x0f,0xb6,0x96,0xb4,0,0,0});
    code.Emit({0x41,0xb8});code.Value<std::uint32_t>(hook);
    code.Emit({0x4c,0x8b,0x8c,0x24});code.Value<std::uint32_t>(0xd0+(hook?0xb8:0x28));
    if (hook) code.Emit({0x48,0x89,0x74,0x24,0x20});else code.Emit({0x48,0xc7,0x44,0x24,0x20,0,0,0,0});
    // The audited constructor return is at +0xb8. Above it are the call's
    // eight-byte return and the common wrapper's 0xa8-byte frame. Pass a slot
    // pointer; the callback reads it only for that exact wrapper origin.
    if (hook) {code.Emit({0x48,0x8d,0x84,0x24});code.Value<std::uint32_t>(0xd0+0xb8+8+0xa8);code.Emit({0x48,0x89,0x44,0x24,0x28});}
    else code.Emit({0x48,0xc7,0x44,0x24,0x28,0,0,0,0});
    code.Emit({0x48,0xb8});code.Value(reinterpret_cast<std::uintptr_t>(callback));code.Emit({0xff,0xd0});
    for (unsigned i=0;i<6;++i) {code.Emit({0xf3,0x0f,0x6f,static_cast<std::uint8_t>(0x84+(i<<3)),0x24});code.Value<std::uint32_t>(0x30+i*16);}
    code.Emit({0x48,0x81,0xc4,0x90,0,0,0,0x41,0x5b,0x41,0x5a,0x41,0x59,0x41,0x58,0x5a,0x59,0x58,0x9d,0xe9});
    if (!IsRel32Reachable(relay+code.bytes.size()+4,resume)) return {};
    code.Value(static_cast<std::int32_t>(reinterpret_cast<std::uintptr_t>(resume)-reinterpret_cast<std::uintptr_t>(relay+code.bytes.size()+4)));
    return code.bytes;
}
bool PrepareGenerationPatch(const TextSection&,GenerationPatchPlan* plan) {plan->direct=SiteAddress("direct_gender");plan->templated=SiteAddress("template_gender");return plan->direct&&plan->templated;}
bool ApplyGenerationPatch(const GenerationPatchPlan& plan) {
    // The manager reconstruction site is audited but deliberately not patched.
    // Script requests with or without a named template use the live constructor.
    for (unsigned hook=1;hook<2;++hook) {
        const auto* site=Site(hook?"template_gender":"direct_gender");auto* address=hook?plan.templated:plan.direct;
        auto* relay=AllocateNear(address,512);if (!relay) return false;
        const auto code=BuildGenerationRelay(hook,relay,address+site->overwrite,reinterpret_cast<const void*>(&ResolveRuntimeGender));
        if (code.empty()||!WriteBytes(relay,code.data(),code.size())||!InstallRelativeJump(address,site->overwrite,relay)) return false;
    }return true;
}
}
