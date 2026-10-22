"""Validate a copied database/configuration without running installation jobs."""
import hashlib,json,os,pathlib,shutil,socket,sqlite3,subprocess,sys,tempfile,time,urllib.request
app=pathlib.Path(sys.argv[1]).resolve();backup=pathlib.Path(sys.argv[2]).resolve();bin=app/'Contents/Resources/bin'
with tempfile.TemporaryDirectory(prefix='atv-migration-check-') as tmp:
 root=pathlib.Path(tmp);data=root/'data'
 shutil.copytree(backup/'application-data/data',data)
 for label,destination in [('plume-data','.config/PlumeImpactor'),('lockdown','.config/atvloadly/lockdown')]:
  if (backup/label).exists():shutil.copytree(backup/label,root/destination)
 db=data/'app.db'
 def read_records():
  with sqlite3.connect(f'file:{db}?mode=ro',uri=True) as c:
   columns=[row[1] for row in c.execute('PRAGMA table_info(installed_apps)')]
   records=c.execute('SELECT '+','.join('"'+name+'"' for name in columns)+' FROM installed_apps ORDER BY id').fetchall()
   return columns,records
 columns,records=read_records()
 settings_file=data/'settings.json';settings=json.loads(settings_file.read_text()) if settings_file.exists() else {}
 settings.setdefault('task',{})['enabled']=False;settings.setdefault('update',{})['check_interval']=0
 settings_file.write_text(json.dumps(settings))
 config=root/'config.yaml';config.write_text(f'server:\n  listen_addr: 127.0.0.1\n  work_dir: {data}\nlog:\n  log_file: {root}/backend.log\n')
 key_hashes={str(p.relative_to(data)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (data/'keys').glob('*') if p.is_file()}
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 env=dict(os.environ,HOME=tmp,XDG_CONFIG_HOME=str(root/'.config'),PATH=str(bin)+':'+os.environ['PATH'])
 with (root/'stdout.log').open('wb') as log:
  started=time.monotonic();process=subprocess.Popen([str(bin/'atvloadly'),'server','-p',str(port),'-c',str(config)],env=env,stdout=log,stderr=log)
  try:
   while time.monotonic()-started<15:
    if process.poll() is not None:raise RuntimeError('Backend exited during copied-data migration')
    try:
     with urllib.request.urlopen(f'http://127.0.0.1:{port}/native/ready',timeout=.5) as r:ready=json.load(r)
     break
    except OSError:time.sleep(.05)
   else:raise RuntimeError('Copied-data migration did not become ready in 15 seconds')
   with sqlite3.connect(f'file:{db}?mode=ro',uri=True) as c:
    migrated=c.execute('SELECT '+','.join('"'+name+'"' for name in columns)+' FROM installed_apps ORDER BY id').fetchall()
    assert migrated==records,'Existing app/source/history columns changed during migration'
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
   for rel,digest in key_hashes.items():assert hashlib.sha256((data/rel).read_bytes()).hexdigest()==digest,'Existing signing/secret key changed'
   with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/apps/installing',timeout=2) as r:queue=json.load(r)
   assert queue.get('data')==[],'An installation was queued during isolated migration'
   print(json.dumps({'copied_data_only':True,'installed_records':len(records),'preserved_existing_columns':len(columns),'existing_keys_preserved':len(key_hashes),'sqlite_integrity':'ok','install_queue':'empty','seconds_to_ready':round(time.monotonic()-started,3)},indent=2))
  finally:
   process.terminate()
   try:process.wait(timeout=5)
   except subprocess.TimeoutExpired:process.kill();process.wait()
