"""Public reporter fixture plus explicitly derived/adversarial controls."""
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from uv_lock_integrity.audit import audit

ROOT = Path(__file__).resolve().parents[1]
ENV = json.loads((ROOT/'examples/linux-python312.json').read_text())


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'project'
        shutil.copytree(ROOT/'examples/valid-exclusion', self.path)

    def replace(self, file, old, new):
        p = self.path/file
        p.write_text(p.read_text().replace(old,new))

    def run_audit(self):
        return audit(self.path, ENV)

    def expect_unknown(self, code=None):
        result = self.run_audit()
        self.assertEqual(result['exit_code'], 2, result)
        if code:
            self.assertIn(code,[e['code'] for e in result['errors']])
        return result

    def test_original_reporter_exclusion(self):
        r = audit(ROOT/'examples/invalid-exclusion', ENV)
        self.assertEqual(r['exit_code'], 1)
        self.assertEqual(r['findings'], [{'manifest':'pyproject.toml','requirement':'numpy!=2.2.4',
            'dependency':'numpy','locked_version':'2.2.4','code':'dependency_constraint_violation'}])

    def test_derived_valid_control(self):
        r = self.run_audit()
        self.assertEqual(r['exit_code'], 0)
        self.assertIn('dependency groups', r['unexamined'])
        self.assertIn('wheel availability', r['unexamined'])
        self.assertIn('build and runtime compatibility', r['unexamined'])

    def test_wrong_exact_pin(self):
        self.replace('pyproject.toml','numpy!=2.2.5','numpy==2.1.0')
        self.assertEqual(self.run_audit()['exit_code'], 1)

    def test_inactive_marker(self):
        self.replace('pyproject.toml','numpy!=2.2.5',"numpy==0; sys_platform == 'win32'")
        self.replace('uv.lock','{ name = "numpy" }',"{ name = 'numpy', marker = \"sys_platform == 'win32'\" }")
        r = self.run_audit()
        self.assertEqual(r['exit_code'], 0, r)
        self.assertEqual(r['checks'][0]['status'],'inactive')

    def test_active_marker(self):
        self.replace('pyproject.toml','numpy!=2.2.5',"numpy==0; sys_platform == 'linux'")
        self.assertEqual(self.run_audit()['exit_code'],1)

    def test_ambiguous_same_name(self):
        with (self.path/'uv.lock').open('a') as p:
            p.write('\n[[package]]\nname="numpy"\nversion="2.1.0"\nsource={registry="https://pypi.org/simple"}\n')
        self.expect_unknown('unsupported_dependency')

    def test_disambiguate_from_edge(self):
        self.test_ambiguous_same_name()
        self.replace('uv.lock','{ name = "numpy" }','{ name = "numpy", version = "2.2.4" }')
        self.assertEqual(self.run_audit()['exit_code'],0)

    def test_disambiguate_from_resolution_markers(self):
        self.test_ambiguous_same_name()
        self.replace('uv.lock','version = "2.2.4"\nsource', 'version = "2.2.4"\nresolution-markers=["sys_platform == \'linux\'"]\nsource')
        self.replace('uv.lock','version="2.1.0"\nsource', 'version="2.1.0"\nresolution-markers=["sys_platform == \'win32\'"]\nsource')
        self.assertEqual(self.run_audit()['exit_code'],0)

    def test_missing_edge(self):
        self.replace('uv.lock','{ name = "numpy" },','')
        self.expect_unknown('unsupported_dependency')

    def test_undeclared_edge(self):
        self.replace('pyproject.toml','"numpy!=2.2.5",','')
        self.expect_unknown('undeclared_lock_edge')

    def test_override(self):
        with (self.path/'pyproject.toml').open('a') as p:
            p.write('\n[tool.uv]\noverride-dependencies=["numpy==2.2.4"]\n')
        self.expect_unknown('unsupported_transform')

    def test_source_override(self):
        with (self.path/'pyproject.toml').open('a') as p:
            p.write('\n[tool.uv.sources]\nnumpy={git="https://example.invalid/numpy"}\n')
        self.expect_unknown('unsupported_dependency')

    def test_unresolved_lock_source(self):
        self.replace('uv.lock','registry = "https://pypi.org/simple"','git = "https://example.invalid/numpy"')
        self.expect_unknown('unsupported_dependency')

    def test_direct_url(self):
        self.replace('pyproject.toml','numpy!=2.2.5','numpy @ https://example.invalid/numpy.whl')
        self.expect_unknown('unsupported_dependency')

    def test_dynamic_dependencies(self):
        self.replace('pyproject.toml','dependencies = [','dynamic = ["dependencies"]\ndependencies = [')
        self.expect_unknown('dynamic_dependencies')

    def test_unknown_revision(self):
        self.replace('uv.lock','revision = 1','revision = 999')
        self.expect_unknown('unsupported_input')

    def test_boolean_format_version(self):
        self.replace('uv.lock','version = 1','version = true')
        self.expect_unknown('unsupported_input')

    def test_partial_finding_remains_inconclusive(self):
        self.test_override()
        self.replace('pyproject.toml','numpy!=2.2.5','numpy==0')
        r=self.expect_unknown('unsupported_transform')
        self.assertEqual(len(r['findings']),1)

    def test_unknown_edge_fields(self):
        self.replace('uv.lock','{ name = "numpy" }','{ name = "numpy", unknown = true }')
        self.expect_unknown('unsupported_dependency')

    def test_malformed_toml(self):
        (self.path/'uv.lock').write_text('package = [')
        self.expect_unknown('input_error')

    def test_wrong_shape(self):
        self.replace('pyproject.toml','"numpy!=2.2.5"','17')
        self.expect_unknown('input_error')

    def test_missing_file(self):
        (self.path/'uv.lock').unlink()
        self.expect_unknown('input_error')

    def test_target_outside_range(self):
        self.replace('uv.lock','>=3.12','>=3.13')
        self.expect_unknown('unsupported_input')

    def test_partial_environment(self):
        self.assertEqual(audit(self.path,{'python_version':'3.12'})['exit_code'],2)

    def test_environment_version_mismatch(self):
        env = {**ENV,'python_full_version':'3.13.2'}
        self.assertEqual(audit(self.path,env)['exit_code'],2)

    def test_extra_marker_inconclusive(self):
        self.replace('uv.lock','{ name = "numpy" }',"{ name = 'numpy', marker = \"extra == 'special'\" }")
        self.expect_unknown()

    def test_read_only_without_network_subprocess_or_project_code(self):
        poison = self.path/'setup.py'
        poison.write_text('raise RuntimeError("Project code must never run")\n')
        before = {p.relative_to(self.path).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in self.path.rglob('*') if p.is_file()}
        with patch.object(socket,'socket',side_effect=AssertionError('network')), patch.object(subprocess,'Popen',side_effect=AssertionError('process')):
            r = self.run_audit()
        self.assertEqual(r['exit_code'],0)
        after = {p.relative_to(self.path).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in self.path.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        self.assertEqual(self.run_audit(),r)

    def test_workspace_member(self):
        with (self.path/'pyproject.toml').open('a') as p:
            p.write('\n[tool.uv.workspace]\nmembers=["packages/*"]\n')
        member=self.path/'packages/member'; member.mkdir(parents=True)
        (member/'pyproject.toml').write_text('[project]\nname="member"\nversion="0.1.0"\ndependencies=["numpy==2.2.4"]\n')
        with (self.path/'uv.lock').open('a') as p:
            p.write('\n[[package]]\nname="member"\nversion="0.1.0"\nsource={editable="packages/member"}\ndependencies=[{name="numpy"}]\n')
        self.assertEqual(self.run_audit()['exit_code'],0)
        (member/'pyproject.toml').write_text((member/'pyproject.toml').read_text().replace('==2.2.4','==2.1.0'))
        r=self.run_audit(); self.assertEqual(r['exit_code'],1)
        self.assertEqual(r['findings'][0]['manifest'],'packages/member/pyproject.toml')

    def test_workspace_escape(self):
        with (self.path/'pyproject.toml').open('a') as p:
            p.write('\n[tool.uv.workspace]\nmembers=["../outside"]\n')
        self.expect_unknown('unsupported_input')

    def test_symlink_input_escape(self):
        outside = Path(self.temp.name)/'outside.toml'
        outside.write_text('[project]\nname="secret"')
        (self.path/'pyproject.toml').unlink()
        (self.path/'pyproject.toml').symlink_to(outside)
        self.expect_unknown('unsupported_input')

    def test_empty_scope(self):
        self.replace('pyproject.toml','"numpy!=2.2.5",','')
        self.replace('uv.lock','{ name = "numpy" },','')
        self.expect_unknown('empty_scope')

    def test_json_cli(self):
        p = subprocess.run([sys.executable,'-m','uv_lock_integrity',str(self.path),'--format','json','--environment',str(ROOT/'examples/linux-python312.json')],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['exit_code'],0)

    def test_bad_environment_cli_schema(self):
        env=self.path/'bad.json'; env.write_text('{')
        p=subprocess.run([sys.executable,'-m','uv_lock_integrity',str(self.path),'--format','json','--environment',str(env)],capture_output=True,text=True)
        self.assertEqual(p.returncode,2)
        r=json.loads(p.stdout)
        self.assertEqual(set(r),set(self.run_audit()))


if __name__ == '__main__':
    unittest.main()
