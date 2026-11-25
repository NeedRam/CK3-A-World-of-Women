from __future__ import annotations
import copy,importlib.util,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
release=module('ufg_release_check',ROOT/'release/check-release.py')
generator=module('ufg_generate_profiles',ROOT/'tools/generate_profiles.py')
class NativeProfileTests(unittest.TestCase):
    def test_native_profile_and_published_agp_match_installer(self):
        result=release.check();self.assertTrue(result['source_checks_ok'],result)
        if result['pending']: self.assertFalse(result['release_ready'])
    def test_profile_generation_is_deterministic_and_independent_of_game_install(self):
        document=json.loads((ROOT/'profiles/ck3-1.21.0.3.json').read_text(encoding='utf-8'))
        first=generator.generate(document);self.assertEqual(first,generator.generate(copy.deepcopy(document)))
        self.assertIn('kAgpSites',first);self.assertNotIn('Program Files',first)
    def test_release_gate_requires_actual_matching_evidence(self):
        relatives=['profiles/ck3-1.21.0.3.json','Installer/release-manifest.json','release/validation.json']
        documents={rel:json.loads((ROOT/rel).read_text(encoding='utf-8')) for rel in relatives}
        native=documents[relatives[0]];validation=documents[relatives[2]];profile=native['profiles'][0];profile['gameplay_verified']=True
        result=validation['profiles'][profile['profile_id']];result['scenarios']=dict.fromkeys(validation['required_scenarios'],'pass');result['runtime_log_evidence']='release/evidence/runtime.log'
        for value in validation['automated'].values():value['status']='pass'
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for relative,document in documents.items():
                path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(document),encoding='utf-8')
            self.assertFalse(release.check(root)['source_checks_ok'])
            evidence=root/result['runtime_log_evidence'];evidence.parent.mkdir(parents=True,exist_ok=True)
            evidence.write_text(profile['profile_id']+'\n'+profile['executable_sha256']+'\nUFG v1.1.0: native patches committed\n',encoding='utf-8')
            self.assertTrue(release.check(root)['release_ready'])
            evidence.write_text('wrong binary; native patches committed',encoding='utf-8');self.assertFalse(release.check(root)['source_checks_ok'])
    def test_fixture_scopes_must_exist_and_callbacks_match_auto_accept(self):
        effects=(ROOT/'native_test_mod/common/scripted_effects/ufg_native_acceptance_effects.txt').read_text(encoding='utf-8-sig')
        self.assertIn('exists = scope:ufg_native_explicit_male_unrelated',effects)
        self.assertIn('exists = scope:ufg_persist_child',effects)
        interactions=(ROOT/'native_test_mod/common/character_interactions/ufg_native_test_interactions.txt').read_text(encoding='utf-8-sig')
        self.assertNotIn('on_accept =',interactions);self.assertEqual(interactions.count('on_auto_accept ='),3)
