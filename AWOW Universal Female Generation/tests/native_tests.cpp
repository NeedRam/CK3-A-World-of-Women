#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <array>
#include "ufg_build_profile.h"
#include "ufg_generation.h"
#include "ufg_relay.h"
#include "ufg_history.h"
using namespace ufg;
unsigned checks=0;
void Check(bool value,const char* message) {++checks;if (!value) {std::fprintf(stderr,"FAIL: %s\n",message);std::exit(1);}}
template<class T> void Put(void* pointer,std::size_t offset,T value) {std::memcpy(static_cast<std::uint8_t*>(pointer)+offset,&value,sizeof(value));}
void ProtectionTests() {
    auto* image=static_cast<std::uint8_t*>(VirtualAlloc(nullptr,0x6a70000,MEM_RESERVE,PAGE_NOACCESS));Check(image!=nullptr,"reserve fixture image");
    for (auto global:{Profile().globals.game_root,Profile().globals.characters,Profile().globals.houses}) Check(VirtualAlloc(image+(global&~std::uintptr_t(4095)),4096,MEM_COMMIT,PAGE_READWRITE)!=nullptr,"commit fixture global");
    std::vector<std::uint8_t> root(0x200),state(0x27000),characters(0x40),houses(0x40),char_slots(64),house_slots(64),candidate(0x200),request(0x200);
    std::array<std::array<std::uint8_t,0x200>,2> player{};std::array<std::array<std::uint8_t,0x40>,3> house{};std::array<std::uint32_t,2> ids{1,2};
    const auto& o=Profile().offsets;
    Put(image,Profile().globals.game_root,root.data());Put(root.data(),o.game_state,state.data());Put(state.data(),o.players,ids.data());Put<std::int32_t>(state.data(),o.player_count,2);
    Put(image,Profile().globals.characters,characters.data());Put(characters.data(),o.database_slots,char_slots.data());Put<std::uint32_t>(characters.data(),o.database_count,4);
    Put(image,Profile().globals.houses,houses.data());Put(houses.data(),o.database_slots,house_slots.data());Put<std::uint32_t>(houses.data(),o.database_count,4);
    for (unsigned i=0;i<2;++i) {Put<std::uint32_t>(player[i].data(),o.character_id,i+1);Put<std::uint32_t>(player[i].data(),o.character_house,i+1);Put(char_slots.data(),(i+1)*16+8,player[i].data());}
    for (unsigned i=0;i<3;++i) {Put<std::uint32_t>(house[i].data(),o.house_id,i+1);Put<std::uint32_t>(house[i].data(),o.house_dynasty,(i+1)*11);Put(house_slots.data(),(i+1)*16+8,house[i].data());}
    Put<std::uint32_t>(candidate.data(),o.character_id,3);Put<std::uint32_t>(candidate.data(),o.character_house,3);Put<std::uint32_t>(request.data(),o.request_house,0xffffffffU);
    auto run=[&](unsigned hook,std::uintptr_t origin,bool* unavailable=nullptr,std::uintptr_t wrapper_origin=0) {return ResolveGenderForImage(candidate.data(),0,hook,origin,request.data(),image,unavailable,wrapper_origin);};
    Check(run(0,0x2ddbbc8)==0,"manager restoration gender is never converted");
    Check(run(1,0x2de53f1)==1,"unrelated non-template script male becomes female");Check(run(1,0x2de53f1)==1,"unrelated template male becomes female");
    Check(run(1,0x2eaca4c)==0,"Ruler Designer preserved");Check(run(0,0x12345)==0,"unknown/birth/save origin preserved");Check(run(9,0x2ddbbc8)==0,"unknown hook preserved");
    Put<std::uint32_t>(candidate.data(),o.character_house,1);Check(run(1,0x2de53f1)==0,"first player dynasty protected");
    Put<std::uint32_t>(candidate.data(),o.character_house,2);Check(run(1,0x2de53f1)==0,"second player dynasty protected");
    Put<std::uint32_t>(candidate.data(),o.character_house,3);Put<std::uint32_t>(request.data(),o.request_house,2);Check(run(1,0x2de53f1)==0,"requested house protects template before assignment");
    Put<std::uint32_t>(request.data(),o.request_house,0xffffffffU);ids[1]=3;Check(run(1,0x2de53f1)==0,"human player protected");ids[1]=2;
    Put<std::uint32_t>(candidate.data(),o.character_house,0xffffffffU);Check(run(1,0x2de53f1)==1,"unrelated lowborn male becomes female");
    bool unavailable=false;Put<std::int32_t>(state.data(),o.player_count,65);Check(run(1,0x2de53f1,&unavailable)==0&&unavailable,"invalid player count preserves request");
    Put<std::int32_t>(state.data(),o.player_count,0);Check(run(1,0x2de53f1,&unavailable)==1&&!unavailable,"valid empty roster still converts");
    Check(run(1,0x2de53f1,&unavailable,0x2eaba44)==0&&!unavailable,"Designer wrapper preserves male before player registration");
    Check(ResolveGenderForImage(candidate.data(),1,1,0x2de53f1,request.data(),image,&unavailable,0x2eaba44)==1&&!unavailable,"Designer wrapper preserves female before player registration");
    Check(run(1,0x2de53f1,&unavailable,0x12345)==1&&!unavailable,"ordinary wrapper caller still converts with empty player roster");
    Check(run(1,0x32cbad2,&unavailable,0x2eaba44)==1&&!unavailable,"Designer exclusion requires the exact immediate wrapper origin");
    Put<std::int32_t>(state.data(),o.player_count,2);Put<std::uint32_t>(request.data(),o.request_house,20);Check(run(1,0x2de53f1,&unavailable)==0&&unavailable,"invalid requested house preserves request");
    Put<std::uint8_t*>(image,Profile().globals.game_root,nullptr);Check(run(1,0x2de53f1,&unavailable)==0&&unavailable,"missing game state preserves request");
    VirtualFree(image,0,MEM_RELEASE);
}
void TransactionTests() {
    auto* memory=static_cast<std::uint8_t*>(VirtualAlloc(nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE));Check(memory!=nullptr,"transaction memory");
    const std::uint8_t replacement[]={0xaa,0xbb};
    BeginPatchTransaction();Check(WriteBytes(memory,replacement,2),"stage first write");Check(!WriteBytes(memory+1,replacement,2),"reject overlapping writes");Check(memory[0]==0,"staging leaves executable unchanged");AbortPatchTransaction();Check(memory[0]==0,"abort unchanged");
    BeginPatchTransaction();Check(WriteBytes(memory,replacement,2),"stage changed preimage");memory[0]=1;Check(!CommitPatchTransaction(),"reject changed original bytes before writes");Check(memory[0]==1,"preflight does not overwrite external changes");memory[0]=0;
    BeginPatchTransaction();Check(WriteBytes(memory,replacement,2)&&WriteBytes(memory+8,replacement,2),"stage transaction");Check(!CommitPatchTransaction(1),"injected commit failure");Check(memory[0]==0&&memory[8]==0,"rollback restored all original bytes");
    BeginPatchTransaction();Check(WriteBytes(memory,replacement,2)&&CommitPatchTransaction(),"commit staged changes");Check(memory[0]==0xaa&&memory[1]==0xbb,"committed bytes verified");
    BeginPatchTransaction();auto* relay=AllocateNear(memory,64);Check(relay!=nullptr,"allocate relay");AbortPatchTransaction();MEMORY_BASIC_INFORMATION info{};VirtualQuery(relay,&info,sizeof(info));Check(info.State==MEM_FREE,"abort releases unused relay");
    VirtualFree(memory,0,MEM_RELEASE);
    Check(!SelectAndValidateProfile(),"unsupported test executable rejected without patching");
}
void ReadinessTests() {
    std::array<std::uint8_t,8> simple{0x74,0x10,0x90};AgpSite site{"simple",0,"74 10 90",0,1,"eb","",0};
    Check(InspectAgpSite(site,simple.data())==DependencyState::Original,"AGP original site detected");simple[0]=0xeb;Check(InspectAgpSite(site,simple.data())==DependencyState::Patched,"AGP replacement verified");simple[2]=0xcc;Check(InspectAgpSite(site,simple.data())==DependencyState::Invalid,"AGP context corruption rejected");
    auto* memory=static_cast<std::uint8_t*>(VirtualAlloc(nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE));std::memset(memory,0x90,64);memory[128]=0x41;memory[129]=0x52;
    AgpSite detour{"detour",0,"90 90 90 90 90 90 90 90",0,7,"","41 52",1};
    Check(InspectAgpSite(detour,memory)==DependencyState::Original,"original AGP detour context");Check(InstallRelativeJump(memory,7,memory+128),"install fixture detour");Check(InspectAgpSite(detour,memory)==DependencyState::Patched,"AGP relay prefix and executable target verified");memory[129]=0x51;Check(InspectAgpSite(detour,memory)==DependencyState::Invalid,"incorrect AGP relay rejected");VirtualFree(memory,0,MEM_RELEASE);
}
void ExecutedRelayTests() {
    for (unsigned hook=0;hook<2;++hook) for (unsigned requested=0;requested<2;++requested) {
        auto* memory=static_cast<std::uint8_t*>(VirtualAlloc(nullptr,8192,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE));Check(memory!=nullptr,"executable harness");
        std::array<std::uint8_t,0x200> character{},request{};std::array<std::uint64_t,24> output{};std::array<std::uint64_t,8> recorded{};
        request[8]=request[0xb4]=static_cast<std::uint8_t>(requested);
        RelayCode callback;callback.Emit({0x49,0xbb});callback.Value(reinterpret_cast<std::uintptr_t>(recorded.data()));
        callback.Emit({0x49,0x89,0x0b,0x49,0x89,0x53,0x08,0x4d,0x89,0x43,0x10,0x4d,0x89,0x4b,0x18,0x48,0x8b,0x44,0x24,0x28,0x49,0x89,0x43,0x20,0x48,0x8b,0xc4,0x83,0xe0,0x0f,0x49,0x89,0x43,0x28});
        callback.Emit({0x48,0x8b,0x44,0x24,0x30,0x49,0x89,0x43,0x30});
        if (hook) callback.Emit({0x48,0x8b,0x00,0x49,0x89,0x43,0x38});
        for (unsigned i=0;i<6;++i) callback.Emit({0x66,0x0f,0xef,static_cast<std::uint8_t>(0xc0+i*9)});
        callback.Emit({0x49,0xba});callback.Value<std::uint64_t>(0xdeadbeef);callback.Emit({0x31,0xc9,0xc3});std::memcpy(memory+4096,callback.bytes.data(),callback.bytes.size());
        const auto relay=BuildGenerationRelay(hook,memory+512,memory+2048,memory+4096);Check(!relay.empty(),"build generation relay");std::memcpy(memory+512,relay.data(),relay.size());
        RelayCode entry;entry.Emit({0x53,0x56,0x41,0x56,0x48,0x81,0xec,0x80,0x01,0,0,0x48,0x8b,0xd9,0x48,0x8b,0xf2,0x4c,0x8b,0xf2,0x4c,0x89,0x84,0x24,0xc0,0,0,0});
        entry.Emit({0x48,0xb8});entry.Value<std::uint64_t>(0x142ddbbc8);entry.Emit({0x48,0x89,0x84,0x24});entry.Value<std::uint32_t>(hook?0xb8:0x28);
        entry.Emit({0x48,0xb8});entry.Value<std::uint64_t>(0x142eaba44);entry.Emit({0x48,0x89,0x84,0x24});entry.Value<std::uint32_t>(0xb8+8+0xa8);
        entry.Emit({0x49,0xba});entry.Value<std::uint64_t>(0x12345678);entry.Emit({0x49,0xb9});entry.Value<std::uint64_t>(0x9876);
        for (unsigned i=0;i<6;++i) {entry.Emit({0xf3,0x0f,0x6f,static_cast<std::uint8_t>(5+(i<<3))});const auto after=memory+entry.bytes.size()+4;entry.Value(static_cast<std::int32_t>((memory+6144)-after));}
        entry.Emit({0x31,0xc0});Check(entry.Finish(memory,memory+512),"write relay entry");
        RelayCode tail;tail.Emit({0x4c,0x8b,0x9c,0x24,0xc0,0,0,0,0x49,0x89,0x03,0x9c,0x58,0x49,0x89,0x43,0x08,0x4d,0x89,0x53,0x10,0x4d,0x89,0x4b,0x18});
        for (unsigned i=0;i<6;++i) {tail.Emit({0xf3,0x41,0x0f,0x7f,static_cast<std::uint8_t>(0x83+(i<<3))});tail.Value<std::uint32_t>(64+i*16);}
        tail.Emit({0x48,0x81,0xc4,0x80,0x01,0,0,0x41,0x5e,0x5e,0x5b,0xc3});std::memcpy(memory+2048,tail.bytes.data(),tail.bytes.size());
        std::memset(memory+6144,0xa5,16);FlushInstructionCache(GetCurrentProcess(),memory,8192);
        reinterpret_cast<void(__fastcall*)(void*,void*,void*)>(memory)(character.data(),request.data(),output.data());
        Check(recorded[0]==reinterpret_cast<std::uintptr_t>(character.data())&&recorded[1]==requested&&recorded[2]==hook,"executed relay callback arguments");Check(recorded[3]==0x142ddbbc8,"correct original return-address stack offset");Check(recorded[4]==(hook?reinterpret_cast<std::uintptr_t>(request.data()):0),"template request or direct null fifth argument");Check(recorded[5]==8,"Win64 callback stack alignment");
        Check(hook?(recorded[6]!=0&&recorded[7]==0x142eaba44):recorded[6]==0,"sixth argument identifies audited outer wrapper return slot");
        Check(output[0]==requested&&(output[1]&0x40)!=0&&output[2]==0x12345678&&output[3]==0x9876,"relay restores GPR and flags, retains native RAX result");
        for (unsigned i=0;i<12;++i) Check(output[8+i]==0xa5a5a5a5a5a5a5a5ULL,"relay restores every volatile XMM register");
        VirtualFree(memory,0,MEM_RELEASE);
    }
}
void ExecutedHistoryTests() {
    for (unsigned locked=0;locked<2;++locked) for (unsigned initial=0;initial<2;++initial) {
        auto* memory=static_cast<std::uint8_t*>(VirtualAlloc(nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE));
        std::array<std::uint8_t,0x200> character{},request{};
        character[Profile().offsets.gender]=static_cast<std::uint8_t>(initial);
        character[Profile().offsets.gender_lock]=static_cast<std::uint8_t>(locked);
        const auto relay=BuildHistoryGenderRelay(memory+512,memory+2048);
        Check(!relay.empty(),"build history relay");std::memcpy(memory+512,relay.data(),relay.size());
        RelayCode entry;
        entry.Emit({0x55,0x53,0x41,0x57,0x48,0x81,0xec,0x90,0,0,0,0x48,0x8b,0xec,0x48,0x8b,0xda,0x45,0x33,0xff,0x48,0x89,0x4d,0x7f});
        Check(entry.Finish(memory,memory+512),"history harness entry");
        const std::uint8_t tail[]={0x0f,0xb6,0x80,0xa1,0x01,0,0,0x48,0x81,0xc4,0x90,0,0,0,0x41,0x5f,0x5b,0x5d,0xc3};
        std::memcpy(memory+2048,tail,sizeof(tail));FlushInstructionCache(GetCurrentProcess(),memory,4096);
        const auto actual=reinterpret_cast<unsigned(__fastcall*)(void*,void*)>(memory)(character.data(),request.data());
        Check(actual==(locked?initial:1),"executed history lock and female override");VirtualFree(memory,0,MEM_RELEASE);
    }
    auto* memory=static_cast<std::uint8_t*>(VirtualAlloc(nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE));
    const auto code=BuildHistorySpouseRelay(memory,memory+512);std::memcpy(memory,code.data(),code.size());
    const std::uint8_t tail[]={0x41,0x8b,0xc1,0xc3};std::memcpy(memory+512,tail,sizeof(tail));FlushInstructionCache(GetCurrentProcess(),memory,4096);
    for (unsigned mode=0;mode<3;++mode) Check(reinterpret_cast<unsigned(__fastcall*)(void*,void*,void*,unsigned)>(memory)(nullptr,nullptr,nullptr,mode)==2,"executed ordinary, matrilineal and same-sex history mode");
    VirtualFree(memory,0,MEM_RELEASE);
}
int main() {ProtectionTests();TransactionTests();ReadinessTests();ExecutedRelayTests();ExecutedHistoryTests();std::printf("PASS: %u native checks, including 4 generation and 7 history executed-relay cases.\n",checks);}
