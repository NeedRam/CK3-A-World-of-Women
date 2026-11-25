#pragma once

#include <cstdint>

#include "ufg_patch_runtime.h"

namespace ufg {

struct GenerationPatchPlan {
	std::uint8_t* direct;
	std::uint8_t* templated;
};

std::uint8_t ResolveGenderForImage(const void* character, std::uint8_t requested, unsigned hook, std::uintptr_t origin_rva, const void* request, const std::uint8_t* base, bool* unavailable = nullptr, std::uintptr_t wrapper_origin_rva = 0);
std::vector<std::uint8_t> BuildGenerationRelay(unsigned hook, std::uint8_t* relay, const void* resume, const void* callback);
bool PrepareGenerationPatch(const TextSection& text, GenerationPatchPlan* plan);
bool ApplyGenerationPatch(const GenerationPatchPlan& plan);

} // namespace ufg
