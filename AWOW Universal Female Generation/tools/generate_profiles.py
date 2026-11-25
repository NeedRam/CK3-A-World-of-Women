"""Generate native profile constants; the game executable is not a build input."""
import argparse,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def generate(document):
    assert document['schema_version']==1 and document['release_version']=='1.1.0'
    assert len(document['profiles'])==1
    p=document['profiles'][0]
    assert re.fullmatch('[0-9a-f]{64}',p['executable_sha256'])
    lines=['// Generated from the canonical UFG profile. Do not edit.','#pragma once','namespace ufg {']
    def array(name,ctype,rows):
        lines.append(f'inline const {ctype} {name}[] = {{')
        lines.extend('{'+','.join(json.dumps(v) if isinstance(v,str) and not v.startswith('0x') else str(v) for v in row)+'},' for row in rows)
        lines.append('};')
    array('kSites','NativeSite',[(s['id'],s['rva'],s['original'],s['overwrite'],s['resume_rva']) for s in p['sites']])
    array('kValidation','NativeSite',[(s['id'],s['rva'],s['original'],0,'0x0') for s in p['validation_sites']])
    array('kCalls','NativeCall',[(s['id'],s['call_rva'],s['target_rva'],s['prologue']) for s in p['call_targets']])
    array('kReferences','NativeReference',[(s['id'],s['rva'],s['original'],s['displacement_offset'],s['instruction_size'],s['target_rva']) for s in p['rip_references']])
    array('kAgpSites','AgpSite',[(s['id'],s['rva'],s['original'],s['patch_offset'],s['overwrite'],s['replacement'],s['relay_prefix'],1 if s['kind']=='detour' else 0) for s in p['agp_readiness']])
    for key,values in p['origins'].items():lines.append(f'inline const std::uintptr_t kOrigins_{key}[] = '+'{'+','.join(values)+'};')
    lines.append('inline const NativeProfile kProfile = {'+','.join(json.dumps(p[k]) for k in ('profile_id','version','executable_sha256','original_dxcompiler_sha256'))+','+','.join(json.dumps(p['agp'][k]) for k in ('version','proxy_sha256','payload_sha256'))+', {'+','.join(str(v) for v in p['offsets'].values())+'}, {'+','.join(p['globals'].values())+'}};')
    lines.append('}')
    return '\n'.join(lines)+'\n'
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output');args=parser.parse_args()
    document=json.loads((ROOT/'profiles/ck3-1.21.0.3.json').read_text(encoding='utf-8'))
    Path(args.output).write_text(generate(document),encoding='utf-8')
