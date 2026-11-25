#pragma once
#include "ufg_patch_runtime.h"
namespace ufg {
struct RelayCode {
    std::vector<std::uint8_t> bytes;
    void Emit(std::initializer_list<std::uint8_t> data) {bytes.insert(bytes.end(),data);}
    template<class T> void Value(T value) {const auto* data=reinterpret_cast<const std::uint8_t*>(&value);bytes.insert(bytes.end(),data,data+sizeof(value));}
    bool JumpTo(std::uint8_t* memory,const void* target) {
        Emit({0xe9});const auto* after=memory+bytes.size()+4;
        if (!IsRel32Reachable(after,target)) return false;
        Value(static_cast<std::int32_t>(reinterpret_cast<std::uintptr_t>(target)-reinterpret_cast<std::uintptr_t>(after)));
        return true;
    }
    bool Finish(std::uint8_t* memory,const void* target) { return JumpTo(memory,target)&&WriteBytes(memory,bytes.data(),bytes.size()); }
};
}
