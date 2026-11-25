"""Gate UFG packaging on exact identities and recorded acceptance."""
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def check(root=ROOT):
    native=json.loads((root/'profiles/ck3-1.21.0.3.json').read_text(encoding='utf-8'))
    manifest=json.loads((root/'Installer/release-manifest.json').read_text(encoding='utf-8'))
    validation=json.loads((root/'release/validation.json').read_text(encoding='utf-8'))
    errors=[];pending=[];profiles=native['profiles']
    if not profiles or len({p['executable_sha256'] for p in profiles})!=len(profiles):errors.append('missing or ambiguous native profile')
    native_release=manifest.get('native_release',{})
    if manifest['schema_version']!=2:errors.append('installer manifest schema mismatch')
    if native['release_version']!=native_release.get('version'):errors.append('native profile and pinned native release version disagree')
    if manifest['release']['version']!='1.1.1':errors.append('installer package release must be 1.1.1')
    for key in ('version','repository','tag','source_commit','archive_url','archive_sha256'):
        if not native_release.get(key):errors.append('pinned native release metadata is incomplete')
    if native['compatibility_basis']!='exact_executable_and_original_dxcompiler_sha256':errors.append('compatibility must use exact file identities')
    expected={(p['profile_id'],p['version'],p['executable_sha256'],p['original_dxcompiler_sha256']) for p in profiles}
    actual={(b['profile_id'],b['id'],b['executable_sha256'],b['original_dxcompiler_sha256']) for b in manifest['target']['supported_builds']}
    if expected!=actual:errors.append('native/installer executable identities disagree')
    for p in profiles:
        ident=p['profile_id']
        if p['version']!='1.21.0.3':errors.append('this release supports CK3 1.21.0.3 only')
        if {s['id'] for s in p['sites']}!={'direct_gender','template_gender','history_gender','history_spouse'}:errors.append('required native hook missing')
        candidates=[b for b in manifest['compatible_agp_builds'] if b['executable_sha256']==p['executable_sha256'] and b['proxy_sha256']==p['agp']['proxy_sha256'] and b['payload_sha256']==p['agp']['payload_sha256'] and b['original_dxcompiler_sha256']==p['original_dxcompiler_sha256']]
        native_candidates=[b for b in candidates if b['version']==p['agp']['version']]
        package_candidates=[b for b in candidates if b['version']==manifest['release']['version']]
        if len(native_candidates)!=1 or len(package_candidates)!=1:errors.append('published AGP dependency identity/version mapping mismatch')
        if not p['static_verified']:pending.append(ident+': static audit')
        evidence=validation['profiles'].get(ident,{})
        runtime=evidence.get('runtime_log_evidence')
        if not p['gameplay_verified'] or not runtime:pending.append(ident+': gameplay/runtime evidence')
        if runtime:
            path=(root/runtime).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():errors.append('runtime evidence missing or outside repository')
            else:
                log=path.read_text(encoding='utf-8-sig')
                if not all(value in log for value in (ident,p['executable_sha256'],'UFG v1.1.0: native patches committed')):errors.append('runtime evidence does not match native profile')
        for scenario in validation['required_scenarios']:
            if evidence.get('scenarios',{}).get(scenario)!='pass':pending.append(ident+': '+scenario)
    for name,result in validation['automated'].items():
        if result.get('status')!='pass':pending.append('automated: '+name)
    return {'source_checks_ok':not errors,'release_ready':not errors and not pending,'errors':errors,'pending':pending}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--allow-incomplete',action='store_true');args=parser.parse_args();result=check();print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['source_checks_ok'] and (args.allow_incomplete or result['release_ready']) else 1)
