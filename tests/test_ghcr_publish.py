"""Run the actual publisher shell with a fake Docker CLI; no registry mutations."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=yaml.safe_load((ROOT/'.github/workflows/service.yml').read_text())
PUBLISH=next(step['run'] for step in WORKFLOW['jobs']['publish']['steps']
             if step.get('name')=='Publish immutable commit image')

DOCKER='''#!/usr/bin/env python3
import json, os, sys
args=sys.argv[1:]
with open(os.environ['NARX_DOCKER_CALLS'],'a') as output:output.write(json.dumps(args)+'\\n')
case=os.environ['NARX_TEST_CASE']
if args[:2]==['image','inspect']:
    print('sha256:'+'a'*64)
elif args[:3]==['buildx','imagetools','inspect']:
    if '--format' in args:print('sha256:'+'b'*64)
    elif '@' not in args[3] and case in {'missing','tampered'}:
        print('manifest unknown',file=sys.stderr);sys.exit(1)
    elif case=='denied':
        print('401 Unauthorized',file=sys.stderr);sys.exit(1)
    elif case=='offline':
        print('unexpected status 503 Service Unavailable',file=sys.stderr);sys.exit(1)
    else:
        config='c' if case=='conflict' or case=='tampered' and '@' in args[3] else 'a'
        print(json.dumps({'config':{'digest':'sha256:'+config*64}}))
elif args[0] not in {'tag','push'}:raise SystemExit('Unexpected fake Docker invocation')
'''


class GhcrPublish(unittest.TestCase):
    def execute(self, case):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'bin').mkdir();(root/'release').mkdir()
            docker=root/'bin/docker';docker.write_text(DOCKER);docker.chmod(0o700)
            calls=root/'calls.jsonl'; output=root/'output'; environ=root/'env'
            env=dict(os.environ, PATH=str(root/'bin')+os.pathsep+os.environ['PATH'],
                     NARX_DOCKER_CALLS=str(calls),NARX_TEST_CASE=case,
                     COMPONENT='frontend',IMAGE_TAG='narx-check-frontend:fixture',
                     GITHUB_SHA='d'*40,GITHUB_REPOSITORY='Narx-Space-Prod/commerce-frontend',
                     GITHUB_RUN_ID='123',GITHUB_OUTPUT=str(output),GITHUB_ENV=str(environ))
            result=subprocess.run(['bash','-e','-o','pipefail','-c',PUBLISH],cwd=root,
                                  env=env,text=True,capture_output=True)
            return result,[json.loads(line) for line in calls.read_text().splitlines()],output.read_text() if output.exists() else ''

    def test_new_image_is_pushed_and_exact_digest_is_recorded(self):
        result,calls,output=self.execute('missing')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(sum(c[0]=='push' for c in calls),1)
        self.assertIn('image=ghcr.io/narx-space-prod/commerce-frontend\n',output)
        self.assertIn('digest=sha256:'+'b'*64,output)

    def test_matching_commit_image_is_reused_without_push(self):
        result,calls,output=self.execute('existing')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(any(c[0] in {'tag','push'} for c in calls))
        self.assertIn('digest=sha256:',output)

    def test_conflicting_tag_auth_error_and_outage_fail_without_push(self):
        for case in ['conflict','denied','offline']:
            with self.subTest(case=case):
                result,calls,output=self.execute(case)
                self.assertNotEqual(result.returncode,0)
                self.assertFalse(any(c[0]=='push' for c in calls))
                self.assertEqual(output,'')

    def test_final_digest_mismatch_is_not_exported_or_signed(self):
        result,_,output=self.execute('tampered')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Published digest does not match',result.stderr)
        self.assertEqual(output,'')


if __name__=='__main__':unittest.main()
