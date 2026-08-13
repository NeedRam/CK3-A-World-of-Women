#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include "ufg_generation.h"

#include <cstring>
#include <vector>

namespace ufg {
namespace {

constexpr std::size_t kCharacterIdOffset = 0x18;
constexpr std::size_t kCharacterGenderOffset = 0x199;
constexpr std::size_t kCharacterHouseIdOffset = 0x150;
constexpr std::uint32_t kInvalidCharacterId = 0xffffffffU;
constexpr std::uint32_t kInvalidObjectId = 0xffffffffU;
constexpr std::uintptr_t kIsHumanPlayerRva = 0x28BCEB0;
constexpr std::uintptr_t kIsPartOfPlayerLegacyRva = 0x2601A80;
constexpr std::uintptr_t kGameStateGlobalRva = 0x570E068;
constexpr std::uintptr_t kCharacterDatabaseGlobalRva = 0x570C130;
constexpr std::uintptr_t kHouseDatabaseGlobalRva = 0x570C408;
constexpr std::size_t kGameStateOffset = 0xa0;
constexpr std::size_t kCurrentPlayersOffset = 0x1d560;
constexpr std::size_t kCurrentPlayerCountOffset = 0x1d56c;
constexpr std::size_t kRequestHouseIdOffset = 0xa8;
constexpr std::size_t kHouseIdOffset = 0x10;
constexpr std::size_t kHouseDynastyIdOffset = 0x2c;
constexpr std::uintptr_t kRulerDesignerTemplateCallerRva = 0x26fa75e;

const std::uint8_t direct_gender[] = {
	0x41, 0x0F, 0xB6, 0x46, 0x08,
	0x88, 0x81, 0x99, 0x01, 0x00, 0x00,
	0x48, 0x8B, 0x5C, 0x24, 0x30
};
const char direct_gender_mask[] = "xxxxxxxxxxxxxxxx";

const std::uint8_t template_gender[] = {
	0x0F, 0xB6, 0x86, 0xB4, 0x00, 0x00, 0x00,
	0x88, 0x83, 0x99, 0x01, 0x00, 0x00,
	0x48, 0x8B, 0x15, 0x00, 0x00, 0x00, 0x00
};
const char template_gender_mask[] = "xxxxxxxxxxxxxxxx????";

enum class HookId : std::uint32_t {
	DirectRequest,
	TemplateRequest,
	Count
};

enum class CandidateRegister {
	Rcx,
	Rbx
};

enum class RequestedSource {
	R14Plus8,
	RsiPlusB4
};

using IsHumanPlayer_t = bool(__fastcall*)(std::uint32_t);
using IsPartOfPlayerLegacy_t = bool(__fastcall*)(const void*, std::uint32_t);

bool IsSupportedOrigin(HookId hook, std::uintptr_t origin_rva) {
	switch (hook) {
	case HookId::DirectRequest:
		return origin_rva == 0x2644e98 || origin_rva == 0x2644ec3;
	case HookId::TemplateRequest:
		return origin_rva == 0x264eb51 || origin_rva == 0x2741d85 || origin_rva == 0x2efb52e;
	default:
		return false;
	}
}

bool IsHumanPlayer(const std::uint8_t* base, std::uint32_t character_id) {
	if (character_id == kInvalidCharacterId) {
		return false;
	}
	const auto function = reinterpret_cast<IsHumanPlayer_t>(base + kIsHumanPlayerRva);
	return function(character_id);
}

void* ResolveDatabaseObject(
	const std::uint8_t* base,
	std::uintptr_t database_global_rva,
	std::uint32_t object_id,
	std::size_t object_id_offset) {
	if (object_id == kInvalidObjectId) {
		return nullptr;
	}
	auto* database = ReadAt<std::uint8_t*>(base, database_global_rva);
	if (database == nullptr) {
		return nullptr;
	}
	const auto index = object_id & 0x00ffffffU;
	if (index >= ReadAt<std::uint32_t>(database, 0x2c)) {
		return nullptr;
	}
	auto* slots = ReadAt<std::uint8_t*>(database, 0x20);
	if (slots == nullptr) {
		return nullptr;
	}
	auto* object = ReadAt<std::uint8_t*>(slots + static_cast<std::size_t>(index) * 16, 8);
	if (object == nullptr || ReadAt<std::uint32_t>(object, object_id_offset) != object_id) {
		return nullptr;
	}
	return object;
}

void* ResolveCharacter(const std::uint8_t* base, std::uint32_t character_id) {
	return ResolveDatabaseObject(base, kCharacterDatabaseGlobalRva, character_id, kCharacterIdOffset);
}

void* ResolveHouse(const std::uint8_t* base, std::uint32_t house_id) {
	return ResolveDatabaseObject(base, kHouseDatabaseGlobalRva, house_id, kHouseIdOffset);
}

bool GetCurrentPlayers(const std::uint8_t* base, const std::uint32_t** ids, std::int32_t* count) {
	auto* root = ReadAt<void*>(base, kGameStateGlobalRva);
	if (root == nullptr) {
		return false;
	}
	auto* state = ReadAt<std::uint8_t*>(root, kGameStateOffset);
	if (state == nullptr) {
		return false;
	}
	*ids = ReadAt<const std::uint32_t*>(state, kCurrentPlayersOffset);
	*count = ReadAt<std::int32_t>(state, kCurrentPlayerCountOffset);
	return *ids != nullptr && *count > 0 && *count <= 64;
}

bool IsRequestedHouseInPlayerDynasty(const std::uint8_t* base, const void* request) {
	if (request == nullptr) {
		return false;
	}
	auto* requested_house = ResolveHouse(base, ReadAt<std::uint32_t>(request, kRequestHouseIdOffset));
	if (requested_house == nullptr) {
		return false;
	}
	const auto requested_dynasty_id = ReadAt<std::uint32_t>(requested_house, kHouseDynastyIdOffset);
	if (requested_dynasty_id == kInvalidObjectId) {
		return false;
	}

	const std::uint32_t* ids = nullptr;
	std::int32_t count = 0;
	if (!GetCurrentPlayers(base, &ids, &count)) {
		return false;
	}
	for (std::int32_t index = 0; index < count; ++index) {
		auto* player = ResolveCharacter(base, ids[index]);
		if (player == nullptr) {
			continue;
		}
		auto* player_house = ResolveHouse(base, ReadAt<std::uint32_t>(player, kCharacterHouseIdOffset));
		if (player_house != nullptr &&
			ReadAt<std::uint32_t>(player_house, kHouseDynastyIdOffset) == requested_dynasty_id) {
			return true;
		}
	}
	return false;
}

bool IsInPlayerDynasty(const std::uint8_t* base, const void* character) {
	const std::uint32_t* ids = nullptr;
	std::int32_t count = 0;
	if (!GetCurrentPlayers(base, &ids, &count)) {
		return false;
	}
	const auto function = reinterpret_cast<IsPartOfPlayerLegacy_t>(base + kIsPartOfPlayerLegacyRva);
	for (std::int32_t index = 0; index < count; ++index) {
		if (function(character, ids[index])) {
			return true;
		}
	}
	return false;
}

extern "C" void __fastcall ResolveRuntimeGender(
	void* character,
	std::uint8_t requested,
	std::uint32_t raw_hook,
	std::uintptr_t origin,
	const void* request,
	std::uintptr_t wrapper_caller) {
	if (character == nullptr || raw_hook >= static_cast<std::uint32_t>(HookId::Count)) {
		return;
	}
	auto* base = reinterpret_cast<std::uint8_t*>(GetModuleHandleW(nullptr));
	const auto hook = static_cast<HookId>(raw_hook);
	const auto origin_rva = origin - reinterpret_cast<std::uintptr_t>(base);
	const auto wrapper_caller_rva = wrapper_caller == 0 ? 0 :
		wrapper_caller - reinterpret_cast<std::uintptr_t>(base);
	std::uint8_t resolved = requested;
	if (IsSupportedOrigin(hook, origin_rva)) {
		const auto character_id = ReadAt<std::uint32_t>(character, kCharacterIdOffset);
		const bool ruler_designer = hook == HookId::TemplateRequest &&
			wrapper_caller_rva == kRulerDesignerTemplateCallerRva;
		const bool preserve = ruler_designer ||
			IsHumanPlayer(base, character_id) ||
			IsInPlayerDynasty(base, character) ||
			(hook == HookId::TemplateRequest && IsRequestedHouseInPlayerDynasty(base, request));
		if (!preserve) {
			resolved = 1;
		}
	}
	std::memcpy(static_cast<std::uint8_t*>(character) + kCharacterGenderOffset, &resolved, sizeof(resolved));
}

void Append(std::vector<std::uint8_t>* code, std::initializer_list<std::uint8_t> bytes) {
	code->insert(code->end(), bytes.begin(), bytes.end());
}

template <typename T>
void AppendValue(std::vector<std::uint8_t>* code, T value) {
	const auto* bytes = reinterpret_cast<const std::uint8_t*>(&value);
	code->insert(code->end(), bytes, bytes + sizeof(value));
}

bool InstallGenderRelay(
	std::uint8_t* site,
	std::size_t replaced_size,
	std::size_t return_address_stack_offset,
	CandidateRegister candidate,
	RequestedSource requested,
	HookId hook) {
	auto* relay = AllocateNear(site, 192);
	if (relay == nullptr) {
		return false;
	}

	std::vector<std::uint8_t> code;
	Append(&code, { 0x9C, 0x50, 0x51, 0x52, 0x41, 0x50, 0x41, 0x51, 0x41, 0x52, 0x41, 0x53, 0x48, 0x83, 0xEC, 0x30 });
	if (candidate == CandidateRegister::Rbx) {
		Append(&code, { 0x48, 0x8B, 0xCB });
	}
	if (requested == RequestedSource::R14Plus8) {
		Append(&code, { 0x41, 0x0F, 0xB6, 0x56, 0x08 });
	} else {
		Append(&code, { 0x0F, 0xB6, 0x96, 0xB4, 0x00, 0x00, 0x00 });
	}
	Append(&code, { 0x41, 0xB8 });
	AppendValue(&code, static_cast<std::uint32_t>(hook));
	Append(&code, { 0x4C, 0x8B, 0x8C, 0x24 });
	AppendValue(&code, static_cast<std::uint32_t>(0x70 + return_address_stack_offset));
	if (requested == RequestedSource::R14Plus8) {
		Append(&code, { 0x4C, 0x89, 0x74, 0x24, 0x20 });
	} else {
		Append(&code, { 0x48, 0x89, 0x74, 0x24, 0x20 });
	}
	if (requested == RequestedSource::RsiPlusB4) {
		// The template constructor is called through a common wrapper. Its
		// caller distinguishes Ruler Designer from ordinary template generation.
		Append(&code, { 0x48, 0x8B, 0x84, 0x24, 0x98, 0x01, 0x00, 0x00 });
		Append(&code, { 0x48, 0x89, 0x44, 0x24, 0x28 });
	} else {
		Append(&code, { 0x33, 0xC0, 0x48, 0x89, 0x44, 0x24, 0x28 });
	}
	Append(&code, { 0x48, 0xB8 });
	AppendValue(&code, reinterpret_cast<std::uintptr_t>(&ResolveRuntimeGender));
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

} // namespace

bool PrepareGenerationPatch(const TextSection& text, GenerationPatchPlan* plan) {
	const Pattern direct_pattern{ direct_gender, direct_gender_mask, sizeof(direct_gender) };
	const Pattern template_pattern{ template_gender, template_gender_mask, sizeof(template_gender) };
	const auto direct = FindPattern(text, direct_pattern);
	const auto templated = FindPattern(text, template_pattern);
	if (direct.size() != 1 || templated.size() != 1) {
		Log("UFG Generation: signature mismatch; no changes made.");
		return false;
	}
	plan->direct = direct[0];
	plan->templated = templated[0];
	return true;
}

bool ApplyGenerationPatch(const GenerationPatchPlan& plan) {
	const bool direct = InstallGenderRelay(
		plan.direct, 11, 0x28, CandidateRegister::Rcx, RequestedSource::R14Plus8, HookId::DirectRequest);
	const bool templated = InstallGenderRelay(
		plan.templated, 13, 0xa8, CandidateRegister::Rbx, RequestedSource::RsiPlusB4, HookId::TemplateRequest);
	if (!direct || !templated) {
		Log("UFG Generation: unable to install generation patches.");
		return false;
	}
	Log("UFG Generation: eligible direct and template character requests now resolve female.");
	return true;
}

} // namespace ufg
