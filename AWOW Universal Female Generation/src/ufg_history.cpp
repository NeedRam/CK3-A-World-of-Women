#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include "ufg_history.h"

#include <cstring>
#include <vector>

namespace ufg {
namespace {

constexpr std::size_t kCharacterGenderOffset = 0x199;
constexpr std::size_t kCharacterGenderLockOffset = 0x19c;

const std::uint8_t history_gender[] = {
	0x0F, 0xB6, 0x83, 0x51, 0x01, 0x00, 0x00,
	0x40, 0x38, 0xB9, 0x9C, 0x01, 0x00, 0x00,
	0x75, 0x0D, 0x88, 0x81, 0x99, 0x01, 0x00, 0x00
};
const char history_gender_mask[] = "xxxxxxxxxxxxxxxxxxxxxx";

const std::uint8_t history_spouse[] = {
	0x48, 0x89, 0x5C, 0x24, 0x08,
	0x48, 0x89, 0x74, 0x24, 0x10,
	0x48, 0x89, 0x7C, 0x24, 0x18,
	0x4C, 0x89, 0x64, 0x24, 0x20,
	0x55, 0x41, 0x56, 0x41, 0x57,
	0x48, 0x8D, 0xAC, 0x24, 0x10, 0xFF, 0xFF, 0xFF,
	0x48, 0x81, 0xEC, 0xF0, 0x01, 0x00, 0x00,
	0x45, 0x8B, 0xF1
};
const char history_spouse_mask[] = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";

void Append(std::vector<std::uint8_t>* code, std::initializer_list<std::uint8_t> bytes) {
	code->insert(code->end(), bytes.begin(), bytes.end());
}

template <typename T>
void AppendValue(std::vector<std::uint8_t>* code, T value) {
	const auto* bytes = reinterpret_cast<const std::uint8_t*>(&value);
	code->insert(code->end(), bytes, bytes + sizeof(value));
}

extern "C" void __fastcall ForceHistoryGender(
	void* character,
	const void*,
	std::uint8_t,
	std::uintptr_t) {
	if (character == nullptr || ReadAt<std::uint8_t>(character, kCharacterGenderLockOffset) != 0) {
		return;
	}
	const std::uint8_t female = 1;
	std::memcpy(static_cast<std::uint8_t*>(character) + kCharacterGenderOffset, &female, sizeof(female));
}

bool InstallHistoryGenderRelay(std::uint8_t* site) {
	constexpr std::size_t replaced_size = 22;
	auto* relay = AllocateNear(site, 160);
	if (relay == nullptr) {
		return false;
	}

	std::vector<std::uint8_t> code;
	Append(&code, { 0x9C, 0x50, 0x51, 0x52, 0x41, 0x50, 0x41, 0x51, 0x41, 0x52, 0x41, 0x53, 0x48, 0x83, 0xEC, 0x30 });
	Append(&code, { 0x48, 0x8B, 0xD3 });
	Append(&code, { 0x44, 0x0F, 0xB6, 0x83, 0x51, 0x01, 0x00, 0x00 });
	Append(&code, { 0x4C, 0x8B, 0x8C, 0x24 });
	AppendValue(&code, static_cast<std::uint32_t>(0x258));
	Append(&code, { 0x48, 0xB8 });
	AppendValue(&code, reinterpret_cast<std::uintptr_t>(&ForceHistoryGender));
	Append(&code, { 0xFF, 0xD0, 0x48, 0x83, 0xC4, 0x30, 0x41, 0x5B, 0x41, 0x5A, 0x41, 0x59, 0x41, 0x58, 0x5A, 0x59, 0x58, 0x9D, 0xE9 });
	const std::size_t jump_immediate = code.size();
	AppendValue<std::int32_t>(&code, 0);
	if (!IsRel32Reachable(relay + jump_immediate + 4, site + replaced_size)) {
		return false;
	}
	const auto displacement = static_cast<std::int32_t>((site + replaced_size) - (relay + jump_immediate + 4));
	std::memcpy(code.data() + jump_immediate, &displacement, sizeof(displacement));
	return WriteBytes(relay, code.data(), code.size()) && InstallRelativeJump(site, replaced_size, relay);
}

bool InstallHistorySpouseRelay(std::uint8_t* site) {
	auto* relay = AllocateNear(site, 32);
	if (relay == nullptr) {
		return false;
	}
	std::uint8_t code[] = {
		0x48, 0x89, 0x5C, 0x24, 0x08,
		0x41, 0xB9, 0x02, 0x00, 0x00, 0x00,
		0xE9, 0x00, 0x00, 0x00, 0x00
	};
	if (!IsRel32Reachable(relay + sizeof(code), site + 5)) {
		return false;
	}
	const auto displacement = static_cast<std::int32_t>((site + 5) - (relay + sizeof(code)));
	std::memcpy(code + 12, &displacement, sizeof(displacement));
	return WriteBytes(relay, code, sizeof(code)) && InstallRelativeJump(site, 5, relay);
}

} // namespace

bool PrepareHistoryPatch(const TextSection& text, HistoryPatchPlan* plan) {
	const Pattern gender_pattern{ history_gender, history_gender_mask, sizeof(history_gender) };
	const Pattern spouse_pattern{ history_spouse, history_spouse_mask, sizeof(history_spouse) };
	const auto gender = FindPattern(text, gender_pattern);
	const auto spouse = FindPattern(text, spouse_pattern);
	if (gender.size() != 1 || spouse.size() != 1) {
		Log("UFG History: signature mismatch; no changes made.");
		return false;
	}
	plan->gender = gender[0];
	plan->spouse = spouse[0];
	return true;
}

bool ApplyHistoryPatch(const HistoryPatchPlan& plan) {
	if (!InstallHistoryGenderRelay(plan.gender) || !InstallHistorySpouseRelay(plan.spouse)) {
		Log("UFG History: unable to install history patches.");
		return false;
	}
	Log("UFG History: history characters resolve female and history spouse commands use the same-sex relation mode.");
	return true;
}

} // namespace ufg
