#!/usr/bin/env python3
"""HET-35 explicit phases: prepare, pause, final-restore, promote, retire, rollback.
Rollback is safe only BEFORE target writes; after target writes reverse-restore first.
"""
import argparse,json,pathlib,subprocess,yaml
P=pathlib.Path('/opt/qwntik-postiz/het35'); ROOT=P.parent
IMAGE='sha256:1257feb5521d4f9f7982a5963ba52747f6c7ab8d7518fd319fcf2cf0a3030067'
NET='qwntik-postiz-managed-db'
def run(a,cwd=None):
 r=subprocess.run(a,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if r.returncode:raise RuntimeError(a[0]+' failed '+r.stderr.decode()[-1000:])
 return r.stdout.decode()
def dc(args):return run(['docker','compose','-f',str(ROOT/'compose.yaml')]+args)
ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['prepare','pause','final-restore','promote','retire','rollback-before-writes']);a=ap.parse_args()
if a.phase=='prepare':
 if not (P/'compose.original.yaml').exists():
  (P/'compose.original.yaml').write_bytes((ROOT/'compose.yaml').read_bytes());(P/'compose.original.yaml').chmod(0o600)
 original=yaml.safe_load((P/'compose.original.yaml').read_text());c=yaml.safe_load((P/'compose.original.yaml').read_text())
 assert c['services']['postiz']['image']==IMAGE
 if subprocess.run(['docker','network','inspect',NET],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:run(['docker','network','create','--internal',NET])
 for project in ['postiz-central','postiz-temporal']:
  d=pathlib.Path('/opt/quantic-impact/clients')/project/'supabase/docker';f=d/'docker-compose.override.yml';b=P/(project+'-override.original.yml')
  if not b.exists():b.write_bytes(f.read_bytes())
  o=yaml.safe_load(b.read_text());o.setdefault('networks',{})['postiz-managed']={'external':True,'name':NET}
  o['services'].setdefault('db',{})['networks']={'default':{},'postiz-managed':{'aliases':[project+'-db']}}
  f.write_text(yaml.safe_dump(o,sort_keys=False));run(['docker','compose','-p',project,'up','-d','--no-deps','db'],cwd=d)
 c.setdefault('networks',{})['postiz-managed']={'external':True,'name':NET}
 app=c['services']['postiz'];app['environment']['DATABASE_URL']='postgresql://postiz_app:'+(P/'app-password.txt').read_text().strip()+'@postiz-central-db:57322/postgres'
 if isinstance(app['networks'],list):app['networks'].append('postiz-managed')
 else:app['networks']['postiz-managed']={}
 app.get('depends_on',{}).pop('postiz-postgres',None)
 t=c['services']['temporal'];assert t['image']=='temporalio/auto-setup@sha256:607d68caa111338d754771efb876c92dfcdae06d056e4530bb31cd0f37406e6a';env=t['environment'];env=dict(x.split('=',1) for x in env) if isinstance(env,list) else env
 env.update({'DB_PORT':'58322','POSTGRES_USER':'postiz_temporal','POSTGRES_PWD':(P/'temporal/app-password.txt').read_text().strip(),'POSTGRES_SEEDS':'postiz-temporal-db','DBNAME':'postgres','SKIP_SCHEMA_SETUP':'true','SKIP_DB_CREATE':'true','SKIP_DEFAULT_NAMESPACE_CREATION':'true','SKIP_ADD_CUSTOM_SEARCH_ATTRIBUTES':'true'});t['environment']=env
 if isinstance(t['networks'],list):t['networks'].append('postiz-managed')
 else:t['networks']['postiz-managed']={}
 t.get('depends_on',{}).pop('temporal-postgresql',None)
 for old in ['postiz-postgres','temporal-postgresql']:c['services'][old]['profiles']=['retired-postgresql']
 # Assert immutable app image and all unrelated app configuration remain unchanged.
 expected=dict(original['services']['postiz']['environment']);actual=dict(app['environment']);expected.pop('DATABASE_URL');actual.pop('DATABASE_URL');assert expected==actual
 assert app['image']==IMAGE and app['command']==original['services']['postiz']['command']
 (P/'compose.managed.yaml').write_text(yaml.safe_dump(c,sort_keys=False));(P/'compose.managed.yaml').chmod(0o600)
 print('persistent DB-only network + managed compose prepared; production compose untouched')
elif a.phase=='pause':
 run(['docker','compose','-f',str(P/'rehearsal.yaml'),'stop'])
 dc(['stop','postiz','temporal'])
 for n in ['qwntik-postiz-postiz','qwntik-postiz-temporal']:
  assert run(['docker','inspect',n,'--format','{{.State.Running}}']).strip()=='false'
 print('all application and Temporal writers stopped')
elif a.phase=='final-restore':
 run(['python3',str(P/'migrate.py'),'final-restore']);run(['python3',str(P/'temporal-migrate.py'),'final-restore']);print('both final restores + fingerprints PASS')
elif a.phase=='promote':
 for n in ['qwntik-postiz-postiz','qwntik-postiz-temporal']:
  assert run(['docker','inspect',n,'--format','{{.State.Running}}']).strip()=='false'
 for prefix,script in [('', 'migrate.py'),('temporal/','temporal-migrate.py')]:
  import hashlib
  receipt=json.loads((P/(prefix+'final-pass.json')).read_text());assert receipt['script_sha256']==hashlib.sha256((P/script).read_bytes()).hexdigest();assert receipt['source']==receipt['target'];assert receipt['dump_sha256']==hashlib.sha256((P/(prefix+'final.dump')).read_bytes()).hexdigest()
 (ROOT/'compose.yaml').write_bytes((P/'compose.managed.yaml').read_bytes());(ROOT/'compose.yaml').chmod(0o600)
 (P/'target-writes-started').write_text('Target writers may have started. A stale source rollback requires reverse restore first.\n')
 dc(['up','-d','--no-deps','temporal']);dc(['up','-d','--no-deps','postiz'])
 assert run(['docker','inspect','qwntik-postiz-postiz','--format','{{.Image}}']).strip()==IMAGE
 (P/'target-writes-started').write_text('Target writers have started. A stale source rollback requires reverse restore first.\n')
 print('managed database cutover started; immutable app image preserved')
elif a.phase=='retire':
 assert (P/'live-pass.json').exists() and (P/'managed-backup-pass.json').exists()
 # Old Temporal credential appeared in one historical tool result; revoke login.
 run(['docker','exec','qwntik-postiz-temporal-postgresql','psql','-U','temporal','-d','temporal','-v','ON_ERROR_STOP=1','-c','ALTER ROLE temporal NOLOGIN;'])
 dc(['stop','postiz-postgres','temporal-postgresql'])
 print('old PostgreSQL containers stopped; both volumes retained; oldTemporalLOGIN disabled')
else:
 assert not (P/'target-writes-started').exists(),'target accepted writes; reviewed reverse restore is mandatory'
 dc(['stop','postiz','temporal']);(ROOT/'compose.yaml').write_bytes((P/'compose.original.yaml').read_bytes());dc(['up','-d','postiz-postgres','temporal-postgresql']);dc(['up','-d','--no-deps','temporal','postiz']);print('pre-write rollback restored original targets and current patched app')
