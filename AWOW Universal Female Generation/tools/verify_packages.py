"""Verify UFG archive hashes, manifests, provenance and native runtime equivalence."""
import argparse,hashlib,io,json,struct,subprocess,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
def runtime_image(data):
    image=bytearray(data)
    assert image[:2]==b"MZ"
    pe=struct.unpack_from("<I",image,60)[0]
    assert image[pe:pe+4]==b"PE\0\0"
    count=struct.unpack_from("<H",image,pe+6)[0]
    optional_size=struct.unpack_from("<H",image,pe+20)[0]
    assert struct.unpack_from("<H",image,pe+24)[0]==0x20b
    section_table=pe+24+optional_size
    sections=[]
    for index in range(count):
        offset=section_table+40*index
        virtual_size,rva,size,raw=struct.unpack_from("<IIII",image,offset+8)
        sections.append((rva,size,raw))
    def raw_offset(rva):
        return next(raw+rva-start for start,size,raw in sections if start<=rva<start+size)
    debug_rva,debug_size=struct.unpack_from("<II",image,pe+24+112+6*8)
    debug_raw=raw_offset(debug_rva)
    assert debug_size%28==0
    for offset in range(debug_raw,debug_raw+debug_size,28):
        kind,size,address,raw=struct.unpack_from("<IIII",image,offset+12)
        image[offset+4:offset+8]=b"\0"*4
        if kind==16: # IMAGE_DEBUG_TYPE_REPRO: linker build-identity hash only.
            assert size==36 and struct.unpack_from("<I",image,raw)[0]==32
            image[raw+4:raw+size]=b"\0"*(size-4)
    image[pe+8:pe+12]=b"\0"*4 # COFF build timestamp / reproducible-build identity.
    # DOS/Rich metadata can change the PE header's location; compare the actual
    # PE headers and every section descriptor and byte after normalizing only
    # documented non-runtime build-identity fields.
    headers=bytes(image[pe:section_table+40*count])
    contents=tuple(bytes(image[raw:raw+size]) for rva,size,raw in sections)
    return headers,contents

def verify(directory,require_canonical=False):
    manifest=json.loads((ROOT/'Installer/release-manifest.json').read_text(encoding='utf-8'))
    version=manifest['release']['version']
    archives=sorted(directory.glob(f'*v{version}*.zip'));assert len(archives)==3,f'expected exactly three v{version} packages'
    provenances=[json.loads(p.read_text(encoding='utf-8-sig')) for p in directory.glob('*provenance.json')]
    records=[]
    for path in archives:
        content=path.read_bytes();digest=hashlib.sha256(content).hexdigest()
        assert path.with_suffix('.zip.sha256').read_text(encoding='utf-8-sig').split()[0]==digest
        matches=[p for p in provenances if p['artifact']['sha256']==digest];assert len(matches)==1
        provenance=matches[0]
        if require_canonical:
            assert provenance['build']['canonical_release_artifact'] and provenance['validation']['acceptance_complete']
            commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();assert provenance['source']['commit']==commit
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            assert archive.testzip() is None
            files={name:archive.read(name) for name in archive.namelist() if not name.endswith('/')}
            sums=next(n for n in files if n.endswith('/SHA256SUMS.txt'));prefix=sums.removesuffix('SHA256SUMS.txt')
            for line in files[sums].decode('utf-8-sig').splitlines():
                expected,relative=line.split(' *',1);assert hashlib.sha256(files[prefix+relative.replace(chr(92),'/')]).hexdigest()==expected
            for relative in ('dxcompiler.dll','AWOW Universal Female Generation/awow_ufg.dll'):
                expected=next(a['sha256'] for a in manifest['artifacts'] if a['relative_path']==relative)
                assert hashlib.sha256(files[prefix+relative]).hexdigest()==expected,'archive runtime differs from pinned native release'
            for name in files:
                assert not {'native_test_mod','src','tests','ck3.exe','dxcompiler_original.dll','agp_parenthook.dll'}.intersection(PurePosixPath(name).parts)
                if name.endswith('/Installer/release-manifest.json'):
                    manifest=json.loads(files[name])
                    for artifact in manifest['artifacts']:
                        data=files[prefix+artifact['relative_path']];assert hashlib.sha256(data).hexdigest()==artifact['sha256'] and len(data)==artifact['size_bytes']
        records.append({'archive':path.name,'sha256':digest,'files':len(files),'canonical':provenance['build']['canonical_release_artifact'],'acceptance_complete':provenance['validation']['acceptance_complete']})
    return records
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path,nargs='?',default=ROOT/'release/out');parser.add_argument('--require-canonical',action='store_true');args=parser.parse_args()
    print(json.dumps(verify(args.directory,args.require_canonical),indent=2))
