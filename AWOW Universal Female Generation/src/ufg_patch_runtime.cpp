#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <limits>
#include "ufg_patch_runtime.h"
namespace ufg {
namespace {
struct PendingWrite { std::uint8_t* address; std::vector<std::uint8_t> before,after; };
bool staging=false;
std::vector<PendingWrite> pending;
std::vector<void*> allocations;
bool WriteDirect(std::uint8_t* address,const std::uint8_t* bytes,std::size_t count) {
    DWORD old=0;if (!VirtualProtect(address,count,PAGE_EXECUTE_READWRITE,&old)) return false;
    std::memcpy(address,bytes,count);
    const bool copied=!std::memcmp(address,bytes,count);
    const bool flushed=FlushInstructionCache(GetCurrentProcess(),address,count)!=FALSE;
    DWORD ignored=0;const bool restored=VirtualProtect(address,count,old,&ignored)!=FALSE;
    return copied&&flushed&&restored;
}
}
void Log(const char* message) {
    auto path=ExecutableDirectory()+L"awow_ufg.log";
    HANDLE file=CreateFileW(path.c_str(),FILE_APPEND_DATA,FILE_SHARE_READ,nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return;DWORD written=0;
    WriteFile(file,message,static_cast<DWORD>(std::strlen(message)),&written,nullptr);WriteFile(file,"\r\n",2,&written,nullptr);CloseHandle(file);
}
std::wstring ExecutableDirectory() {
    wchar_t path[32768]{};if (!GetModuleFileNameW(nullptr,path,32768)) return {};
    auto* slash=std::wcsrchr(path,L'\\');if (!slash) return {};slash[1]=0;return path;
}
bool ReadMemory(const void* address,void* output,std::size_t size) {
    SIZE_T count=0;return address&&output&&ReadProcessMemory(GetCurrentProcess(),address,output,size,&count)&&count==size;
}
void BeginPatchTransaction() { AbortPatchTransaction();staging=true; }
void AbortPatchTransaction() {
    staging=false;pending.clear();for (auto* allocation:allocations) VirtualFree(allocation,0,MEM_RELEASE);allocations.clear();
}
bool CommitPatchTransaction(std::size_t fault_after) {
    if (!staging) return false;
    for (const auto& write:pending) {
        std::vector<std::uint8_t> actual(write.before.size());
        if (!ReadMemory(write.address,actual.data(),actual.size()) || actual!=write.before) { AbortPatchTransaction();Log("UFG: original bytes changed before commit; no UFG writes made.");return false; }
    }
    staging=false;std::size_t attempted=0;bool ok=true;
    for (const auto& write:pending) {
        if (attempted==fault_after) { ok=false;break; }
        ++attempted;
        if (std::memcmp(write.address,write.before.data(),write.before.size()) || !WriteDirect(write.address,write.after.data(),write.after.size())) { ok=false;break; }
    }
    if (!ok) {
        bool restored=true;while (attempted) { const auto& write=pending[--attempted];restored=WriteDirect(write.address,write.before.data(),write.before.size())&&restored; }
        Log(restored?"UFG: transaction rolled back and verified. Exit without saving.":"UFG: PATCH ROLLBACK FAILED. Exit immediately without saving.");
        // Relays may have been entered before rollback. Keep them resident until exit.
        allocations.clear();pending.clear();return false;
    }
    allocations.clear();pending.clear();return true;
}
bool WriteBytes(std::uint8_t* address,const void* bytes,std::size_t size) {
    if (!address||!bytes||!size) return false;
    if (!staging) return WriteDirect(address,static_cast<const std::uint8_t*>(bytes),size);
    auto start=reinterpret_cast<std::uintptr_t>(address);
    for (const auto& write:pending) {
        auto other=reinterpret_cast<std::uintptr_t>(write.address);
        if (start<other+write.after.size()&&other<start+size) return false;
    }
    std::vector<std::uint8_t> original(size);if (!ReadMemory(address,original.data(),size)) return false;
    const auto* data=static_cast<const std::uint8_t*>(bytes);pending.push_back({address,std::move(original),{data,data+size}});return true;
}
bool IsRel32Reachable(const void* after,const void* target) {
    const auto delta=static_cast<std::int64_t>(reinterpret_cast<std::uintptr_t>(target))-static_cast<std::int64_t>(reinterpret_cast<std::uintptr_t>(after));
    return delta>=INT32_MIN&&delta<=INT32_MAX;
}
void WriteRel32(std::uint8_t* immediate,const void* target) {
    const auto delta=static_cast<std::int32_t>(reinterpret_cast<std::uintptr_t>(target)-reinterpret_cast<std::uintptr_t>(immediate+4));
    WriteBytes(immediate,&delta,4);
}
bool InstallRelativeJump(std::uint8_t* site,std::size_t size,const void* target) {
    if (size<5||!IsRel32Reachable(site+5,target)) return false;
    std::vector<std::uint8_t> bytes(size,0x90);bytes[0]=0xe9;
    const auto delta=static_cast<std::int32_t>(reinterpret_cast<std::uintptr_t>(target)-reinterpret_cast<std::uintptr_t>(site+5));
    std::memcpy(bytes.data()+1,&delta,4);return WriteBytes(site,bytes.data(),bytes.size());
}
bool GetTextSection(TextSection* result) {
    if (!result) return false;auto* base=reinterpret_cast<std::uint8_t*>(GetModuleHandleW(nullptr));
    auto* dos=reinterpret_cast<IMAGE_DOS_HEADER*>(base);if (dos->e_magic!=IMAGE_DOS_SIGNATURE) return false;
    auto* nt=reinterpret_cast<IMAGE_NT_HEADERS64*>(base+dos->e_lfanew);
    if (nt->Signature!=IMAGE_NT_SIGNATURE||nt->OptionalHeader.Magic!=IMAGE_NT_OPTIONAL_HDR64_MAGIC) return false;
    auto* section=IMAGE_FIRST_SECTION(nt);
    for (WORD i=0;i<nt->FileHeader.NumberOfSections;++i,++section) if (!std::memcmp(section->Name,".text",5)) {result->begin=base+section->VirtualAddress;result->size=section->Misc.VirtualSize;return true;}
    return false;
}
bool Matches(const std::uint8_t* address,const Pattern& pattern) {
    if (!address||!pattern.bytes||!pattern.mask) return false;
    for (std::size_t i=0;i<pattern.size;++i) if (pattern.mask[i]=='x'&&address[i]!=pattern.bytes[i]) return false;return true;
}
std::vector<std::uint8_t*> FindPattern(const TextSection& text,const Pattern& pattern) {
    std::vector<std::uint8_t*> result;if (!pattern.size||pattern.size>text.size) return result;
    for (std::size_t i=0;i<=text.size-pattern.size;++i) if (text.begin[i]==pattern.bytes[0]&&Matches(text.begin+i,pattern)) result.push_back(text.begin+i);return result;
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
					if (IsRel32Reachable(target, allocation)) { if (staging) allocations.push_back(allocation); return allocation; }
					VirtualFree(allocation, 0, MEM_RELEASE);
				}
			}
		}
		if (region_end <= address) break;
		address = region_end;
	}
	return nullptr;
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


}
