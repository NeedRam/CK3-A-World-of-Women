#pragma once

#include <cstdint>

#include "ufg_patch_runtime.h"

namespace ufg {

struct HistoryPatchPlan {
	std::uint8_t* gender;
	std::uint8_t* spouse;
};

bool PrepareHistoryPatch(const TextSection& text, HistoryPatchPlan* plan);
bool ApplyHistoryPatch(const HistoryPatchPlan& plan);

} // namespace ufg
