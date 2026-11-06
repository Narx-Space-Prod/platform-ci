"""Exercise the real workflow's report binding and source-identity checks."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
BUILD=yaml.safe_load((ROOT/'.github/workflows/build.yml').read_text())
SONAR=yaml.safe_load((ROOT/'.github/workflows/sonar.yml').read_text())
BIND=next(s['run'] for s in BUILD['jobs']['build']['steps'] if s.get('name')=='Bind analysis reports to this source revision')
CONFIGURE=next(s['run'] for s in SONAR['jobs']['analyze']['steps'] if s.get('name')=='Validate project identity and configure analysis')
SAMPLES={
 'frontend':('lcov.info','SF:src/server.js\nLF:2\nLH:1\nend_of_record\n'),
 'catalogue':('coverage.out','mode: atomic\nboutique/catalogue/main.go:1.1,2.1 2 1\n'),
 'orders':('jacoco.xml','<report><counter type="LINE" missed="1" covered="2"/></report>'),
 'cart':('coverage.xml','<coverage lines-covered="1" lines-valid="2"><sources><source>.</source></sources></coverage>'),
}

class CoverageContract(unittest.TestCase):
 def execute(self,script,root,component,repo):
  env=dict(os.environ,COMPONENT=component,RUNNER_TEMP=str(root),GITHUB_REPOSITORY='Narx-Space-Prod/'+repo,
           GITHUB_SHA='a'*40,GITHUB_STEP_SUMMARY=str(root/'summary'),PROJECT_KEY='narx_'+repo,
           SONAR_ORGANIZATION='narx-space-prod',SONAR_SERVER='https://sonarcloud.io')
  return subprocess.run(['bash','-eu','-o','pipefail','-c',script],cwd=root,env=env,text=True,capture_output=True)

 def test_real_report_formats_and_same_revision_inputs(self):
  for repo,components in [('commerce-frontend',['frontend']),('commerce-catalogue',['catalogue']),('commerce-orders',['orders','cart'])]:
   with self.subTest(repo=repo),tempfile.TemporaryDirectory() as folder:
    root=Path(folder)
    for component in components:
     path=root/'analysis'/component;path.mkdir(parents=True)
     name,text=SAMPLES[component];(path/name).write_text(text)
     result=self.execute(BIND,root,component,repo);self.assertEqual(result.returncode,0,result.stderr)
     path.rename(path.with_name('analysis-'+component))
    result=self.execute(CONFIGURE,root,components[0],repo);self.assertEqual(result.returncode,0,result.stderr)
    config=(root/'narx-sonar.properties').read_text()
    self.assertIn('sonar.qualitygate.wait=true',config)
    self.assertIn('analysis/analysis-',config)
    if 'cart' in components:self.assertIn('<source>cart</source>',(root/'analysis/analysis-cart/coverage.xml').read_text())
    identity=root/'analysis'/('analysis-'+components[0])/'source.json'
    data=json.loads(identity.read_text());data['commit']='b'*40;identity.write_text(json.dumps(data))
    result=self.execute(CONFIGURE,root,components[0],repo)
    self.assertNotEqual(result.returncode,0)
    self.assertIn('do not match',result.stderr)

 def test_artifact_download_paths_are_explicit_for_single_and_multi_component_projects(self):
  downloads=[step for step in SONAR['jobs']['analyze']['steps'] if 'actions/download-artifact@' in step.get('uses','')]
  self.assertEqual(len(downloads),2)
  for step in downloads:
   self.assertNotIn('pattern',step['with'])
   self.assertEqual(step['with']['path'],'analysis/'+step['with']['name'])
  cart=next(step for step in downloads if step['with']['name']=='analysis-cart')
  self.assertEqual(cart['if'],"github.repository == 'Narx-Space-Prod/commerce-orders'")

 def test_empty_missing_and_invalid_reports_fail_closed(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);path=root/'analysis/frontend';path.mkdir(parents=True)
   for contents in [None,'','LF:0\nLH:0\n','LF:1\nLH:2\n']:
    with self.subTest(contents=contents):
     if contents is not None:(path/'lcov.info').write_text(contents)
     result=self.execute(BIND,root,'frontend','commerce-frontend')
     self.assertNotEqual(result.returncode,0)
