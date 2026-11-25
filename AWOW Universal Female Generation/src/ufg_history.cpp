#include "ufg_history.h"
#include "ufg_build_profile.h"
#include "ufg_relay.h"
namespace ufg {
std::vector<std::uint8_t> BuildHistoryGenderRelay(std::uint8_t* relay,const void* resume) {
    RelayCode code;const auto original=ParseHex(Site("history_gender")->original);
    code.bytes.insert(code.bytes.end(),original.begin(),original.begin()+18);
    // Retain the native lock branch and original register/flag effects.
    code.Emit({0x75,0x07,0xc6,0x80});code.Value<std::uint32_t>(static_cast<std::uint32_t>(Profile().offsets.gender));code.Emit({0x01});
    return code.JumpTo(relay,resume)?code.bytes:std::vector<std::uint8_t>{};
}
std::vector<std::uint8_t> BuildHistorySpouseRelay(std::uint8_t* relay,const void* resume) {
    RelayCode code;const auto original=ParseHex(Site("history_spouse")->original);
    code.bytes.insert(code.bytes.end(),original.begin(),original.begin()+5);code.Emit({0x41,0xb9,0x02,0,0,0});
    return code.JumpTo(relay,resume)?code.bytes:std::vector<std::uint8_t>{};
}
bool PrepareHistoryPatch(const TextSection&,HistoryPatchPlan* plan) {plan->gender=SiteAddress("history_gender");plan->spouse=SiteAddress("history_spouse");return plan->gender&&plan->spouse;}
bool ApplyHistoryPatch(const HistoryPatchPlan& plan) {
    auto* gender=AllocateNear(plan.gender,64);auto* spouse=AllocateNear(plan.spouse,32);if (!gender||!spouse) return false;
    const auto first=BuildHistoryGenderRelay(gender,plan.gender+Site("history_gender")->overwrite);
    const auto second=BuildHistorySpouseRelay(spouse,plan.spouse+5);
    return !first.empty()&&!second.empty()&&WriteBytes(gender,first.data(),first.size())&&WriteBytes(spouse,second.data(),second.size())&&InstallRelativeJump(plan.gender,Site("history_gender")->overwrite,gender)&&InstallRelativeJump(plan.spouse,5,spouse);
}
}
