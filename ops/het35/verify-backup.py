#!/usr/bin/env python3
"""Restore both managed backup public schemas into no-network disposable PG17."""
import json,pathlib,subprocess,time
P=pathlib.Path('/opt/qwntik-postiz/het35');B=pathlib.Path('/var/backups/qwntik-postiz/current');C='het35-backup-restore'
def run(a,data=None):
 r=subprocess.run(a,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if r.returncode:raise RuntimeError(a[0]+' '+r.stderr.decode()[-1200:])
 return r.stdout
image=run(['docker','inspect','qwntik-postiz-postiz-postgres','--format','{{.Image}}']).decode().strip()
run(['docker','run','-d','--name',C,'--network','none','--tmpfs','/var/lib/postgresql/data:rw','-e','POSTGRES_PASSWORD=isolated-backup-fixture-only',image])
try:
 for _ in range(60):
  if subprocess.run(['docker','exec',C,'pg_isready','-U','postgres'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
  time.sleep(1)
 else:raise RuntimeError('backup fixture not ready')
 result={}
 for name,filename,script,count in [('app','postiz.dump','migrate.py',89),('temporal','temporal.dump','temporal-migrate.py',37)]:
  run(['docker','exec',C,'createdb','-U','postgres',name])
  dump=B/filename;run(['docker','cp',str(dump),C+':/tmp/backup.dump'])
  toc=run(['docker','exec',C,'pg_restore','-l','/tmp/backup.dump']).decode()
  toc='\n'.join(x for x in toc.splitlines() if not (' SCHEMA - public ' in x or ' COMMENT - SCHEMA public ' in x))+'\n'
  f=P/(name+'-backup-restore.list');f.write_text(toc);run(['docker','cp',str(f),C+':/tmp/backup.list'])
  run(['docker','exec',C,'pg_restore','-U','postgres','-d',name,'--exit-on-error','--single-transaction','--no-owner','--no-acl','--no-comments','--schema=public','-L','/tmp/backup.list','/tmp/backup.dump'])
  code=(P/script).read_text().split('ap=argparse.ArgumentParser()')[0];ns={'__name__':'backup_verify'};exec(code,ns)
  def sql(c,q):return run(['docker','exec','-i',C,'psql','-X','-v','ON_ERROR_STOP=1','-U','postgres','-d',name,'-At'],q.encode()).decode().strip()
  ns['sql']=sql;fp=ns['fingerprint']('fixture');assert len(fp['tables'])==count
  expected=json.loads((P/('final-source.json' if name=='app' else 'temporal/final-source.json')).read_text())
  assert fp['catalog_sha256']==expected['catalog_sha256'] and fp['columns_sha256']==expected['columns_sha256']
  if name=='app':
   # Human state may progress after cutover; backup must retain at least all prior identities.
   assert int(fp['tables']['User'].split(':')[0])>=int(expected['tables']['User'].split(':')[0])
  else:assert sql('',"SELECT curr_version||':'||min_compatible_version||':'||db_name FROM public.schema_version;")=='1.17:1.0:postgres'
  result[name]={'tables':count,'schema_matches':True,'dump_restored':True,'fingerprint':fp}
 (P/'managed-backup-pass.json').write_text(json.dumps(result,indent=2)+'\n')
 print('managed encrypted-backup dumps restore PASS: app89/Temporal37; source schema and Temporal1.17 preserved')
finally:run(['docker','rm','-f',C])
