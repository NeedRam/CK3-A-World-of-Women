from __future__ import annotations
import copy,json,tempfile,unittest,sys
from pathlib import Path
import test_cross_engine as fixtures
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ufg_installer.core import Installer,InstallError
ROOT=Path(__file__).resolve().parents[3]
class MigrationTests(unittest.TestCase):
    def setUp(self): self.fixture=fixtures.CrossEngineTests()
    def setup_target(self,root):
        package=self.fixture.make_package(root);target=self.fixture.make_target(root)
        manifest=json.loads((package/'Installer/release-manifest.json').read_text(encoding='utf-8'));candidate=manifest['compatible_agp_builds'][0]
        state={'schema_version':2,'kind':'agp_install_state','status':'managed_agp','release':{'version':candidate['version']},'target':{'build_id':manifest['target']['supported_builds'][0]['id'],'target_root_kind':'ck3_game_binaries','profile_id':candidate['profile_id']},'baseline':{},'managed_files':[]}
        for key,relative in [('executable','ck3.exe'),('original_dxcompiler','dxcompiler_original.dll')]:
            item=target/relative;state['baseline'][key]={'ownership':'game','relative_path':relative,'sha256':fixtures.digest(item.read_bytes()),'size_bytes':item.stat().st_size}
        for relative in ['dxcompiler.dll','AGP Native Hook/agp_parenthook.dll']:
            item=target/relative;state['managed_files'].append({'relative_path':relative,'ownership':'managed','installed_sha256':fixtures.digest(item.read_bytes()),'installed_size_bytes':item.stat().st_size})
        path=target/'AGP Native Hook/agp-install-state.json';path.write_text(json.dumps(state),encoding='utf-8')
        return package,target,path
    def test_agp_v2_supported_by_both_engines_and_preserved(self):
        for engine_name in ['python','powershell']:
            with self.subTest(engine=engine_name),tempfile.TemporaryDirectory() as temp:
                package,target,path=self.setup_target(Path(temp));before=path.read_bytes()
                engine=Installer(package_root=package,process_checker=lambda:False)
                if engine_name=='python':self.assertEqual(engine.install(target).decision,'proceed')
                else:
                    code,result=self.fixture.run_ps('install',target,package);self.assertEqual((code,result['decision']),(0,'proceed'),result)
                self.assertEqual(path.read_bytes(),before)
                if engine_name=='python':
                    code,result=self.fixture.run_ps('uninstall',target,package);self.assertEqual((code,result['decision']),(0,'proceed'),result)
                else:self.assertEqual(engine.uninstall(target).decision,'proceed')
                self.assertEqual(path.read_bytes(),before)
    def test_legacy_ufg_state_migrates_transactionally_in_both_engines(self):
        for engine_name in ['python','powershell']:
            with self.subTest(engine=engine_name),tempfile.TemporaryDirectory() as temp:
                package,target,_=self.setup_target(Path(temp));engine=Installer(package_root=package,process_checker=lambda:False)
                self.assertEqual(engine.install(target).decision,'proceed')
                path=target/'AWOW Universal Female Generation/ufg-install-state.json';state=json.loads(path.read_text(encoding='utf-8'));state['schema_version']=1;state['$schema']=state['$schema'].replace('-v2','-v1');state['target']['target_root_kind']='steam_game_binaries';state['target'].pop('profile_id')
                for entry in state['baseline'].values():entry['ownership']='steam'
                path.write_text(json.dumps(state),encoding='utf-8');before=path.read_bytes()
                self.assertEqual(engine.install(target).decision,'abort');self.assertEqual(path.read_bytes(),before)
                if engine_name=='python':self.assertEqual(engine.install(target,'UPGRADE_UFG_IN_PLACE').decision,'proceed')
                else:
                    code,result=self.fixture.run_ps('install',target,package,'UPGRADE_UFG_IN_PLACE');self.assertEqual((code,result['decision']),(0,'proceed'),result)
                self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['schema_version'],2)
    def test_agp_v2_mismatched_metadata_is_zero_write_refusal(self):
        with tempfile.TemporaryDirectory() as temp:
            package,target,path=self.setup_target(Path(temp));state=json.loads(path.read_text(encoding='utf-8'));state['target']['profile_id']='wrong-profile';path.write_text(json.dumps(state),encoding='utf-8');before={p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file()}
            engine=Installer(package_root=package,process_checker=lambda:False);self.assertEqual(engine.install(target).decision,'reject')
            code,result=self.fixture.run_ps('install',target,package);self.assertEqual((code,result['decision']),(2,'reject'))
            self.assertEqual({p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file()},before)
    def test_ambiguous_hash_profiles_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            package,target,_=self.setup_target(Path(temp));path=package/'Installer/release-manifest.json';manifest=json.loads(path.read_text(encoding='utf-8'));manifest['target']['supported_builds'].append(copy.deepcopy(manifest['target']['supported_builds'][0]));path.write_text(json.dumps(manifest),encoding='utf-8')
            engine=Installer(package_root=package,process_checker=lambda:False)
            with self.assertRaises(InstallError):engine.install(target)
            code,result=self.fixture.run_ps('install',target,package);self.assertEqual((code,result['decision']),(2,'reject'))

    def test_agp_state_version_selects_matching_candidate_and_is_recorded(self):
        for engine_name in ['python','powershell']:
            with self.subTest(engine=engine_name),tempfile.TemporaryDirectory() as temp:
                package,target,path=self.setup_target(Path(temp));state=json.loads(path.read_text(encoding='utf-8'));state['release']['version']='1.1.1';path.write_text(json.dumps(state),encoding='utf-8')
                engine=Installer(package_root=package,process_checker=lambda:False)
                if engine_name=='python': result=engine.install(target)
                else:
                    code,result=self.fixture.run_ps('install',target,package);self.assertEqual((code,result['decision']),(0,'proceed'),result)
                if engine_name=='python': self.assertEqual(result.decision,'proceed',result.message)
                written=json.loads((target/'AWOW Universal Female Generation/ufg-install-state.json').read_text(encoding='utf-8'))
                self.assertEqual(written['agp_dependency']['version'],'1.1.1')

    def test_unsupported_agp_state_version_is_zero_write_refusal(self):
        with tempfile.TemporaryDirectory() as temp:
            package,target,path=self.setup_target(Path(temp));state=json.loads(path.read_text(encoding='utf-8'));state['release']['version']='9.9.9';path.write_text(json.dumps(state),encoding='utf-8');before={p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file()}
            engine=Installer(package_root=package,process_checker=lambda:False);self.assertEqual(engine.install(target).decision,'reject')
            code,result=self.fixture.run_ps('install',target,package);self.assertEqual((code,result['decision']),(2,'reject'),result)
            self.assertEqual({p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file()},before)
