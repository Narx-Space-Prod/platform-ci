#!/usr/bin/env python3
"""Component integration tests of the already-built runtime, in disposable Docker resources.

Only runner-local dynamically published ports are queried. No kubeconfig, external
application URL, cloud credential, production database or payment key is accepted.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
import unittest
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET

POSTGRES='postgres:16@sha256:1a6ab3f5345eb6dbe04a1349529caabdb0ab09293a09590fad07b2246bfa4b54'
REDIS='redis:7.4-alpine@sha256:892022f9f18c26c92c30e15194d132f90044af87b94a491a75429bbc3982eab1'
PYTHON='python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f'

class Lab:
 def __init__(self,component,image):
  if component not in {'frontend','catalogue','orders','cart'} or not re.fullmatch('narx-check-'+component+':[a-f0-9]{40}',image):
   raise ValueError('Only the current tested component image is accepted')
  if os.environ.get('GITHUB_ACTIONS')!='true':raise ValueError('Run live integration tests on an isolated GitHub-hosted runner')
  self.component,self.image=component,image
  self.name='narx-integration-'+uuid.uuid4().hex[:12];self.containers=[];self.network=False
 def docker(self,*args):
  result=subprocess.run(['docker',*args],text=True,capture_output=True,timeout=180)
  if result.returncode:raise RuntimeError('Docker operation failed: '+args[0]+'\n'+result.stderr[-2000:])
  return result.stdout.strip()
 def start(self,alias,image,env=None,port=None,memory='128m',extra=(),command=()):
  args=['run','--detach','--name',self.name+'-'+alias,'--label','narx.integration='+self.name,
        '--network',self.name,'--network-alias',alias,'--memory',memory,'--cpus','1']
  for key,value in (env or {}).items():args+=['--env',key+'='+value]
  if port:args+=['--publish','127.0.0.1::'+str(port)]
  self.containers.append(self.name+'-'+alias)
  cid=self.docker(*args,*extra,image,*command)
  return cid
 def __enter__(self):
  try:
   self.docker('network','create','--label','narx.integration='+self.name,self.name);self.network=True
   env={}
   if self.component=='cart':
    self.dependency=self.start('redis',REDIS,memory='64m',command=('redis-server','--save','','--appendonly','no'))
    env={'REDIS_URL':'redis://redis:6379/0'}
   elif self.component=='orders':
    self.dependency=self.start('postgres',POSTGRES,{'POSTGRES_DB':'commerce','POSTGRES_USER':'commerce',
       'POSTGRES_PASSWORD':uuid.uuid4().hex},memory='192m',command=('postgres','-c','shared_buffers=32MB','-c','max_connections=30'))
    # Read the test credential from our generated container config without printing it.
    config=json.loads(self.docker('inspect',self.dependency))[0]['Config']['Env']
    password=next(v.split('=',1)[1] for v in config if v.startswith('POSTGRES_PASSWORD='))
    env={'DATABASE_URL':'jdbc:postgresql://postgres:5432/commerce','DATABASE_USER':'commerce',
         'DATABASE_PASSWORD':password,'CART_URL':'http://unused-cart:8082','SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE':'2'}
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
     try:self.docker('exec',self.dependency,'pg_isready','-U','commerce','-d','commerce');break
     except RuntimeError:time.sleep(1)
    else:raise RuntimeError('Disposable PostgreSQL did not become ready')
   else:
    self.dependency=self.start('upstream',PYTHON,memory='64m',extra=('--read-only','--cap-drop','ALL',
       '--mount','type=bind,src='+str(Path(__file__).with_name('upstream.py').resolve())+',dst=/fixture.py,readonly'),
       command=('python','-B','/fixture.py'))
    env={'COMMERCE_URL':'http://upstream:8090'} if self.component=='catalogue' else {
       'CATALOGUE_URL':'http://upstream:8090','CART_URL':'http://upstream:8090','ORDERS_URL':'http://upstream:8090',
       'SESSION_SECRET':uuid.uuid4().hex+uuid.uuid4().hex,'PUBLIC_ORIGIN':'http://integration.invalid'}
   port={'frontend':8080,'catalogue':8081,'cart':8082,'orders':8083}[self.component]
   self.app=self.start('app',self.image,env,port=port,memory='448m' if self.component=='orders' else '128m',
      extra=('--read-only','--tmpfs','/tmp:rw,nosuid,size=64m','--cap-drop','ALL','--security-opt','no-new-privileges'))
   host=self.docker('port',self.app,str(port)+'/tcp').splitlines()[0]
   if not re.fullmatch(r'127\.0\.0\.1:\d+',host):raise ValueError('Test port must stay on runner loopback')
   self.base='http://'+host;self.ready();return self
  except BaseException:
   self.close();raise
 def request(self,path,method='GET',data=None,headers=None):
  request=urllib.request.Request(self.base+path,method=method,
      data=json.dumps(data).encode() if data is not None else None,
      headers={'Content-Type':'application/json',**(headers or {})})
  try:response=urllib.request.urlopen(request,timeout=10)
  except urllib.error.HTTPError as error:response=error
  with response:
   body=response.read().decode();content=json.loads(body) if 'application/json' in response.headers.get('Content-Type','') else body
   return response.status,content,response.headers
 def ready(self):
  deadline=time.monotonic()+120
  while time.monotonic()<deadline:
   try:
    if self.request('/health/ready')[0]==200:return
   except (OSError,ValueError):pass
   time.sleep(1)
  raise RuntimeError('Runtime readiness timed out')
 def close(self):
  for cid in reversed(self.containers):
   subprocess.run(['docker','rm','--force','--volumes',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)
  if self.network:
   subprocess.run(['docker','network','rm',self.name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)
 def __exit__(self,*args):self.close()

class Contracts(unittest.TestCase):
 lab=None
 def register(self):
  credentials={'email':uuid.uuid4().hex+'@integration.invalid','password':'ci-only integration passphrase','name':'CI customer'}
  status,body,_=self.lab.request('/auth/register','POST',credentials)
  self.assertEqual(status,200);self.assertEqual(body['user']['role'],'customer')
  return credentials,body['token']
 def test_successful_runtime_contract(self):
  lab=self.lab
  if lab.component in {'frontend','catalogue'}:
   path='/api/products' if lab.component=='frontend' else '/products'
   status,body,_=lab.request(path);self.assertEqual(status,200);self.assertEqual(body[0]['id'],'ci-book')
   if lab.component=='frontend':self.assertEqual(lab.request('/')[2]['Cache-Control'],'no-store')
  elif lab.component=='cart':
   path='/carts/'+'a'*64
   self.assertEqual(lab.request(path+'/items/ci-book','PUT',{'quantity':2})[0],200)
   self.assertEqual(lab.request(path)[1]['items'],[{'productId':'ci-book','quantity':2}])
   self.assertEqual(lab.request('/carts/'+'b'*64)[1]['items'],[])
  else:
   credentials,token=self.register()
   self.assertEqual(lab.request('/auth/login','POST',credentials)[0],200)
   self.assertEqual(lab.request('/auth/session',headers={'X-Account-Token':token})[1]['user']['email'],credentials['email'])
 def test_invalid_input_and_authorization_boundary(self):
  lab=self.lab
  if lab.component=='frontend':self.assertEqual(lab.request('/api/auth/login','POST',{},headers={'Origin':'https://untrusted.invalid'})[0],403)
  elif lab.component=='catalogue':self.assertEqual(lab.request('/products/missing')[0],404)
  elif lab.component=='cart':self.assertEqual(lab.request('/carts/'+'a'*64+'/items/ci-book','PUT',{'quantity':0})[0],422)
  else:
   self.assertEqual(lab.request('/auth/session')[0],401)
   credentials,token=self.register()
   self.assertEqual(lab.request('/admin/dashboard',headers={'X-Account-Token':token})[0],403)
   credentials['password']='wrong integration passphrase'
   self.assertEqual(lab.request('/auth/login','POST',credentials)[0],401)
 def test_dependency_failure_recovery_or_persisted_session_revocation(self):
  lab=self.lab
  if lab.component=='orders':
   _,token=self.register();headers={'X-Account-Token':token}
   self.assertEqual(lab.request('/auth/logout','POST',{},headers)[0],200)
   self.assertEqual(lab.request('/auth/session',headers=headers)[0],401)
  else:
   lab.docker('stop','--time','2',lab.dependency)
   try:self.assertEqual(lab.request('/health/ready')[0],503)
   finally:lab.docker('start',lab.dependency);lab.ready()
   self.assertEqual(lab.request('/health/ready')[0],200)

class Result(unittest.TextTestResult):
 def startTest(self,test):
  super().startTest(test);self.current=ET.SubElement(self.report,'testcase',name=test.id());self.started=time.monotonic()
 def stopTest(self,test):
  self.current.set('time',str(round(time.monotonic()-self.started,3)));super().stopTest(test)
 def addFailure(self,test,err):
  super().addFailure(test,err);ET.SubElement(self.current,'failure').text=self._exc_info_to_string(err,test)
 def addError(self,test,err):
  super().addError(test,err);ET.SubElement(self.current,'error').text=self._exc_info_to_string(err,test)

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--component',required=True);parser.add_argument('--image',required=True);parser.add_argument('--report',required=True,type=Path);args=parser.parse_args()
 report=ET.Element('testsuite',name=args.component+' component integration');Result.report=report
 try:
  with Lab(args.component,args.image) as lab:
   Contracts.lab=lab;result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Contracts))
   report.set('tests',str(result.testsRun));report.set('failures',str(len(result.failures)));report.set('errors',str(len(result.errors)))
   passed=result.wasSuccessful()
 except Exception as error:
  case=ET.SubElement(report,'testcase',name='integration_environment_setup');ET.SubElement(case,'error').text=str(error)
  report.set('tests','1');report.set('errors','1');passed=False
 finally:
  args.report.parent.mkdir(parents=True,exist_ok=True);ET.ElementTree(report).write(args.report,encoding='utf-8',xml_declaration=True)
 if os.environ.get('GITHUB_STEP_SUMMARY'):
  with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as output:output.write(f'### {args.component} component integration\n\n'+('Passed' if passed else 'FAILED')+' against the tested runtime image and isolated dependencies. JUnit XML retained as an artifact.\n')
 raise SystemExit(0 if passed else 1)
if __name__=='__main__':main()
