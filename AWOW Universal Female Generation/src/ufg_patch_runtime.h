#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

namespace ufg {

struct TextSection {
	std::uint8_t* begin{};
	std::size_t size{};
};

struct Pattern {
	const std::uint8_t* bytes{};
	const char* mask{};
	std::size_t size{};
};

void Log(const char* message);
bool GetTextSection(TextSection* result);
std::vector<std::uint8_t*> FindPattern(const TextSection& section, const Pattern& pattern);
bool Matches(const std::uint8_t* address, const Pattern& pattern);
bool WriteBytes(std::uint8_t* address, const void* bytes, std::size_t size);
bool IsRel32Reachable(const void* source_after_immediate, const void* target);
void WriteRel32(std::uint8_t* immediate, const void* target);
std::uint8_t* AllocateNear(const void* target, std::size_t size);
bool InstallRelativeJump(std::uint8_t* site, std::size_t replaced_size, const void* target);
bool Sha256File(const wchar_t* path, std::string* result);
std::wstring ExecutableDirectory();

template <typename T>
T ReadAt(const void* object, std::size_t offset) {
	T value{};
	if (object != nullptr) {
		std::memcpy(&value, static_cast<const std::uint8_t*>(object) + offset, sizeof(value));
	}
	return value;
}

} // namespace ufg
