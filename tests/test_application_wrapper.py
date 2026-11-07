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
