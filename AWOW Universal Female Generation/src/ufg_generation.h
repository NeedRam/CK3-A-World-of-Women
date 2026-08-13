#pragma once

#include <cstdint>

#include "ufg_patch_runtime.h"

namespace ufg {

struct GenerationPatchPlan {
	std::uint8_t* direct;
	std::uint8_t* templated;
};

bool PrepareGenerationPatch(const TextSection& text, GenerationPatchPlan* plan);
bool ApplyGenerationPatch(const GenerationPatchPlan& plan);

} // namespace ufg
