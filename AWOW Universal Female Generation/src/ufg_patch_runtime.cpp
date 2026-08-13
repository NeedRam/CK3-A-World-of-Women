#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>

#include "ufg_patch_runtime.h"

#include <cstdio>
#include <cstring>
#include <limits>

#pragma comment(lib, "bcrypt.lib")

namespace ufg {

std::wstring ExecutableDirectory() {
	wchar_t path[MAX_PATH]{};
	if (GetModuleFileNameW(nullptr, path, MAX_PATH) == 0) return {};
	wchar_t* separator = std::wcsrchr(path, L'\\');
	if (separator == nullptr) return {};
	separator[1] = L'\0';
	return path;
}

void Log(const char* message) {
	char path[MAX_PATH]{};
	if (GetModuleFileNameA(nullptr, path, MAX_PATH) == 0) return;
	char* separator = std::strrchr(path, '\\');
	if (separator == nullptr) return;
	std::strcpy(separator + 1, "awow_ufg.log");
	HANDLE file = CreateFileA(path, FILE_APPEND_DATA, FILE_SHARE_READ, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
	if (file == INVALID_HANDLE_VALUE) return;
	DWORD written = 0;
	WriteFile(file, message, static_cast<DWORD>(std::strlen(message)), &written, nullptr);
	WriteFile(file, "\r\n", 2, &written, nullptr);
	CloseHandle(file);
}

bool GetTextSection(TextSection* result) {
	if (result == nullptr) return false;
	auto* base = reinterpret_cast<std::uint8_t*>(GetModuleHandleW(nullptr));
	if (base == nullptr) return false;
	auto* dos = reinterpret_cast<IMAGE_DOS_HEADER*>(base);
	if (dos->e_magic != IMAGE_DOS_SIGNATURE) return false;
	auto* nt = reinterpret_cast<IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
	if (nt->Signature != IMAGE_NT_SIGNATURE || nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC) return false;
	auto* section = IMAGE_FIRST_SECTION(nt);
	for (WORD index = 0; index < nt->FileHeader.NumberOfSections; ++index, ++section) {
		if (std::memcmp(section->Name, ".text", 5) == 0) {
			result->begin = base + section->VirtualAddress;
			result->size = section->Misc.VirtualSize;
			return true;
		}
	}
	return false;
}

bool Matches(const std::uint8_t* address, const Pattern& pattern) {
	if (address == nullptr || pattern.bytes == nullptr || pattern.mask == nullptr) return false;
	for (std::size_t index = 0; index < pattern.size; ++index) {
		if (pattern.mask[index] == 'x' && address[index] != pattern.bytes[index]) return false;
	}
	return true;
}

std::vector<std::uint8_t*> FindPattern(const TextSection& section, const Pattern& pattern) {
	std::vector<std::uint8_t*> matches;
	if (pattern.size == 0 || pattern.size > section.size) return matches;
	for (std::size_t offset = 0; offset <= section.size - pattern.size; ++offset) {
		if (section.begin[offset] == pattern.bytes[0] && Matches(section.begin + offset, pattern)) {
			matches.push_back(section.begin + offset);
		}
	}
	return matches;
}

bool WriteBytes(std::uint8_t* address, const void* bytes, std::size_t size) {
	if (address == nullptr || bytes == nullptr || size == 0) return false;
	DWORD old_protection = 0;
	if (!VirtualProtect(address, size, PAGE_EXECUTE_READWRITE, &old_protection)) return false;
	std::memcpy(address, bytes, size);
	FlushInstructionCache(GetCurrentProcess(), address, size);
	DWORD ignored = 0;
	VirtualProtect(address, size, old_protection, &ignored);
	return true;
}

bool IsRel32Reachable(const void* source_after_immediate, const void* target) {
	const auto delta = reinterpret_cast<const std::uint8_t*>(target) -
		reinterpret_cast<const std::uint8_t*>(source_after_immediate);
	return delta >= std::numeric_limits<std::int32_t>::min() && delta <= std::numeric_limits<std::int32_t>::max();
}

void WriteRel32(std::uint8_t* immediate, const void* target) {
	const auto delta = reinterpret_cast<const std::uint8_t*>(target) - (immediate + 4);
	const auto value = static_cast<std::int32_t>(delta);
	std::memcpy(immediate, &value, sizeof(value));
}

std::uint8_t* AllocateNear(const void* target, std::size_t size) {
	SYSTEM_INFO info{};
	GetSystemInfo(&info);
	const auto granularity = static_cast<std::uintptr_t>(info.dwAllocationGranularity);
	const auto center = reinterpret_cast<std::uintptr_t>(target);
	const auto minimum = center > 0x7fff0000ULL ? center - 0x7fff0000ULL : 0;
	const auto maximum = center + 0x7fff0000ULL;
	for (std::uintptr_t address = center; address < maximum;) {
		MEMORY_BASIC_INFORMATION region{};
		if (VirtualQuery(reinterpret_cast<const void*>(address), &region, sizeof(region)) == 0) break;
		const auto region_start = reinterpret_cast<std::uintptr_t>(region.BaseAddress);
		const auto region_end = region_start + region.RegionSize;
		if (region.State == MEM_FREE) {
			const auto candidate = (region_start + granularity - 1) & ~(granularity - 1);
			if (candidate >= minimum && candidate < maximum && region_end >= candidate + size) {
				if (auto* allocation = static_cast<std::uint8_t*>(VirtualAlloc(
					reinterpret_cast<void*>(candidate), size, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE))) {
					if (IsRel32Reachable(target, allocation)) return allocation;
					VirtualFree(allocation, 0, MEM_RELEASE);
				}
			}
		}
		if (region_end <= address) break;
		address = region_end;
	}
	return nullptr;
}

bool InstallRelativeJump(std::uint8_t* site, std::size_t replaced_size, const void* target) {
	if (replaced_size < 5 || !IsRel32Reachable(site + 5, target)) return false;
	std::vector<std::uint8_t> patch(replaced_size, 0x90);
	patch[0] = 0xE9;
	const auto displacement = static_cast<std::int32_t>(reinterpret_cast<const std::uint8_t*>(target) - (site + 5));
	std::memcpy(patch.data() + 1, &displacement, sizeof(displacement));
	return WriteBytes(site, patch.data(), patch.size());
}

bool Sha256File(const wchar_t* path, std::string* result) {
	if (path == nullptr || result == nullptr) return false;
	HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
		nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
	if (file == INVALID_HANDLE_VALUE) return false;
	BCRYPT_ALG_HANDLE algorithm = nullptr;
	BCRYPT_HASH_HANDLE hash = nullptr;
	std::vector<std::uint8_t> object;
	std::vector<std::uint8_t> digest;
	bool ok = false;
	DWORD object_size = 0, digest_size = 0, value_size = 0;
	if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0) goto cleanup;
	if (BCryptGetProperty(algorithm, BCRYPT_OBJECT_LENGTH, reinterpret_cast<PUCHAR>(&object_size), sizeof(object_size), &value_size, 0) < 0) goto cleanup;
	if (BCryptGetProperty(algorithm, BCRYPT_HASH_LENGTH, reinterpret_cast<PUCHAR>(&digest_size), sizeof(digest_size), &value_size, 0) < 0) goto cleanup;
	object.resize(object_size);
	digest.resize(digest_size);
	if (BCryptCreateHash(algorithm, &hash, object.data(), object_size, nullptr, 0, 0) < 0) goto cleanup;
	for (;;) {
		std::uint8_t buffer[1 << 16]{};
		DWORD read = 0;
		if (!ReadFile(file, buffer, sizeof(buffer), &read, nullptr)) goto cleanup;
		if (read == 0) break;
		if (BCryptHashData(hash, buffer, read, 0) < 0) goto cleanup;
	}
	if (BCryptFinishHash(hash, digest.data(), digest_size, 0) < 0) goto cleanup;
	{
		static constexpr char hex[] = "0123456789ABCDEF";
		result->resize(digest.size() * 2);
		for (std::size_t index = 0; index < digest.size(); ++index) {
			(*result)[index * 2] = hex[digest[index] >> 4];
			(*result)[index * 2 + 1] = hex[digest[index] & 0x0f];
		}
	}
	ok = true;

cleanup:
	if (hash != nullptr) BCryptDestroyHash(hash);
	if (algorithm != nullptr) BCryptCloseAlgorithmProvider(algorithm, 0);
	CloseHandle(file);
	return ok;
}

} // namespace ufg
