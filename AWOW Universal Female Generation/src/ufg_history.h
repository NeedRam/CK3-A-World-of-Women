#pragma once

#include <cstdint>

#include "ufg_patch_runtime.h"

namespace ufg {

struct HistoryPatchPlan {
	std::uint8_t* gender;
	std::uint8_t* spouse;
};

std::vector<std::uint8_t> BuildHistoryGenderRelay(std::uint8_t* relay, const void* resume);
std::vector<std::uint8_t> BuildHistorySpouseRelay(std::uint8_t* relay, const void* resume);
bool PrepareHistoryPatch(const TextSection& text, HistoryPatchPlan* plan);
bool ApplyHistoryPatch(const HistoryPatchPlan& plan);

} // namespace ufg
