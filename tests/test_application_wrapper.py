"""Security and dependency contracts for the single application entry workflow."""
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=yaml.safe_load((ROOT/'.github/workflows/application.yml').read_text())

class ApplicationWrapper(unittest.TestCase):
 def test_builds_are_read_only_and_publication_waits_for_quality(self):
  jobs=WORKFLOW['jobs']
  self.assertEqual(WORKFLOW['permissions'],{'contents':'read'})
  self.assertEqual(jobs['quality']['needs'],['build','cart'])
  self.assertIn("needs.build.result == 'success'",jobs['quality']['if'])
  self.assertIn("needs.cart.result == 'skipped'",jobs['quality']['if'])
  for name in ('build','cart'):
   self.assertNotIn('secrets',jobs[name])
   self.assertNotIn('permissions',jobs[name])
  for name,build in [('publish','build'),('cart-publish','cart')]:
   self.assertEqual(jobs[name]['needs'],[build,'quality'])
   self.assertIn("github.ref == 'refs/heads/main'",jobs[name]['if'])
   self.assertIn("github.event_name == 'push'",jobs[name]['if'])
   self.assertIn('!cancelled()',jobs[name]['if'])
   self.assertIn(f"needs.{build}.result == 'success'",jobs[name]['if'])
   self.assertIn("needs.quality.result == 'success'",jobs[name]['if'])
   self.assertNotIn('secrets',jobs[name])
   self.assertTrue(jobs[name]['uses'].endswith('service.yml@35ff4ae9d506db00dbc2adc7ec027382bbe99db3'))

 def test_optional_cart_does_not_block_a_successful_primary_release(self):
  jobs=WORKFLOW['jobs']
  self.assertEqual(jobs['cart']['if'],"inputs.application == 'orders'")
  guard=jobs['delivery']['if']
  for name in ('publish','cart-publish'):
   self.assertIn(f"needs.{name}.result == 'success'",guard)
   self.assertIn(f"needs.{name}.result == 'skipped'",guard)
  self.assertIn('!cancelled()',guard)
  self.assertNotIn('inherit',str(jobs))
  self.assertEqual(set(jobs['quality']['secrets']),{'SONAR_TOKEN'})
  self.assertEqual(set(jobs['delivery']['secrets']),{'NARX_RELEASE_APP_PRIVATE_KEY'})

class MasterIntakeContract(unittest.TestCase):
 def test_main_starts_master_before_build_finishes_and_does_not_dispatch_twice(self):
  jobs=WORKFLOW['jobs']
  intake=jobs['intake']
  self.assertEqual(intake['needs'],'validate')
  self.assertIn("github.event_name == 'push'",intake['if'])
  self.assertIn("github.ref == 'refs/heads/main'",intake['if'])
  self.assertEqual(set(intake['secrets']),{'NARX_RELEASE_APP_PRIVATE_KEY'})
  self.assertFalse(jobs['delivery']['with']['dispatch-delivery'])
  self.assertEqual(jobs['build']['needs'],'validate')

class VersionedEvidenceContract(unittest.TestCase):
 def test_evidence_is_separate_from_privileged_steps_and_publication_waits_for_records(self):
  jobs=WORKFLOW['jobs']
  self.assertEqual(jobs['test-evidence']['needs'],['build','cart'])
  self.assertEqual(jobs['quality-evidence']['needs'],'quality')
  self.assertEqual(jobs['publication-evidence']['needs'],['quality','publish','cart-publish','delivery'])
  for name in ('test-evidence','quality-evidence','publication-evidence'):
   self.assertNotIn('secrets',jobs[name])
   self.assertNotIn('permissions',jobs[name])
   self.assertTrue(jobs[name]['uses'].endswith('/evidence.yml'))
   self.assertIn('!cancelled()',jobs[name]['if'])
 def test_emitter_rejects_failed_gates_and_binds_run_attempt(self):
  import os,tempfile
  from unittest.mock import patch
  workflow=yaml.safe_load((ROOT/'.github/workflows/evidence.yml').read_text())
  script=workflow['jobs']['record']['steps'][0]['run'].split("python3 - <<'PY'\n",1)[1].rsplit('\nPY',1)[0]
  env={'GATE':'tests','APPLICATION':'orders','PRIMARY':'success','COMPANION':'success','RELEASES':'[]','GITHUB_REPOSITORY':'Narx-Space-Prod/commerce-orders','GITHUB_SHA':'b'*40,'GITHUB_RUN_ID':'12','GITHUB_RUN_ATTEMPT':'2'}
  import json
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,env):
   old=os.getcwd()
   try:
    os.chdir(folder);exec(compile(script,'emitter','exec'),{})
    self.assertEqual(json.loads(Path('gate.json').read_text())['runAttempt'],2)
    for field,value in [('PRIMARY','failure'),('COMPANION','skipped')]:
     with patch.dict(os.environ,{field:value}):
      with self.assertRaises(AssertionError):exec(compile(script,'emitter','exec'),{})
   finally:os.chdir(old)
