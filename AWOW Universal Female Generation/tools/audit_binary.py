"""Read-only audit of an exact CK3 PE against UFG's native profiles.

No game files are distributed or modified. The audit uses only Python's standard
library; disassembly provenance and gameplay evidence are recorded separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

DEFAULT_PROFILES = Path(__file__).resolve().parents[1] / 'profiles/ck3-1.21.0.3.json'


class PE:
    def __init__(self, data: bytes):
        self.data = data
        if data[:2] != b"MZ":
            raise ValueError("not a PE executable")
        header = struct.unpack_from("<I", data, 0x3C)[0]
        if data[header:header + 4] != b"PE\0\0":
            raise ValueError("invalid PE signature")
        machine, count = struct.unpack_from("<HH", data, header + 4)
        optional_size = struct.unpack_from("<H", data, header + 20)[0]
        if machine != 0x8664 or struct.unpack_from("<H", data, header + 24)[0] != 0x20B:
            raise ValueError("UFG requires Windows x64 PE32+")
        self.sections = []
        for index in range(count):
            offset = header + 24 + optional_size + index * 40
            name = data[offset:offset + 8].rstrip(b"\0").decode("ascii")
            virtual_size, rva, raw_size, raw = struct.unpack_from("<IIII", data, offset + 8)
            self.sections.append((name, rva, min(virtual_size, raw_size), raw))
        text = next(section for section in self.sections if section[0] == ".text")
        self.text_rva, size, raw = text[1:]
        self.text = data[raw:raw + size]

    def at(self, rva: int, size: int) -> bytes:
        for _, start, count, raw in self.sections:
            if start <= rva and rva + size <= start + count:
                return self.data[raw + rva - start:raw + rva - start + size]
        raise ValueError(f"RVA {rva:#x} is outside file-backed sections")



def audit(path: Path, document: dict) -> dict:
    data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
    result={'executable_sha256':digest,'ok':False,'checks':[]}
    profiles=[p for p in document['profiles'] if p['executable_sha256']==digest]
    if len(profiles)!=1:result['error']='executable must match exactly one native profile';return result
    p=profiles[0];result['profile_id']=p['profile_id'];pe=PE(data)
    ranges=[]
    for site in p['sites']+p['validation_sites']+p['agp_readiness']:
        original=bytes.fromhex(site['original']);rva=int(site['rva'],0)
        valid=pe.at(rva,len(original))==original and pe.text.count(original)==1
        valid=valid and pe.text_rva<=rva and rva+len(original)<=pe.text_rva+len(pe.text)
        result['checks'].append({'id':site['id'],'ok':valid})
    for call in p['call_targets']:
        rva=int(call['call_rva'],0);insn=pe.at(rva,5);target=rva+5+struct.unpack('<i',insn[1:])[0]
        expected=int(call['target_rva'],0);prologue=bytes.fromhex(call['prologue'])
        result['checks'].append({'id':call['id'],'ok':insn[0]==0xe8 and target==expected and pe.at(expected,len(prologue))==prologue})
    for ref in p['rip_references']:
        rva=int(ref['rva'],0);original=bytes.fromhex(ref['original']);actual=pe.at(rva,len(original));offset=ref['displacement_offset']
        target=rva+ref['instruction_size']+struct.unpack_from('<i',actual,offset)[0]
        result['checks'].append({'id':ref['id'],'ok':actual==original and target==int(ref['target_rva'],0)})
    for site in p['sites']:
        start=int(site['rva'],0);end=start+site['overwrite']
        if site.get('kind')!='validation' and (site['overwrite']<5 or end!=int(site['resume_rva'],0)):result['checks'].append({'id':site['id']+'_length','ok':False})
        for dependency in p['agp_readiness']:
            other=int(dependency['rva'],0)+dependency['patch_offset']
            assert max(start,other)>=min(end,other+dependency['overwrite']),'UFG/AGP patch overlap'
    result['ok']=all(c['ok'] for c in result['checks']);return result
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('executable',type=Path);args=parser.parse_args()
    result=audit(args.executable,json.loads(DEFAULT_PROFILES.read_text(encoding='utf-8')))
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['ok'] else 1)
