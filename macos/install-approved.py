"""One-time legacy cutover. Run only after explicit approval; never used by CI."""
import argparse, hashlib, json, os, pathlib, plistlib, re, shutil, sqlite3, subprocess, time, urllib.request

p=argparse.ArgumentParser()
p.add_argument('application',type=pathlib.Path)
p.add_argument('--approved',action='store_true',help='requires explicit human approval to replace the installed app')
a=p.parse_args()
if not a.approved: raise SystemExit('Installation requires explicit approval; no changes made.')
home=pathlib.Path.home();root=home/'Library/Application Support/ATVLoadly'
target=home/'Applications/ATVLoadly.app';source=a.application.resolve()
if source==target.resolve(): raise SystemExit('Source must be a separate verified build.')
if (root/'updates/pending.json').exists(): raise SystemExit('An update transaction is pending; resolve it before legacy migration.')
subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(source)],check=True)
for name in ('atvloadly','plumesign','update-agent'):
 subprocess.run(['/usr/bin/lipo','-verify_arch','arm64',str(source/'Contents/Resources/bin'/name)],check=True)
with urllib.request.urlopen('http://127.0.0.1:5533/api/apps/installing',timeout=3) as response:
 state=json.load(response)
if state.get('code')!=200 or not isinstance(state.get('data'),list) or state['data']:
 raise SystemExit('The legacy install queue is busy or cannot be verified; installation postponed.')
# comm excludes process arguments, which can contain signing credentials.
processes=subprocess.check_output(['/bin/ps','-axo','pid=,comm='],text=True)
if any(line.strip().endswith('/plumesign') for line in processes.splitlines()):
 raise SystemExit('A signing-engine process is running; wait for it to finish and retry.')
os.umask(0o077)
backup=root/'migration-backups'/time.strftime('%Y%m%d-%H%M%S')
backup.mkdir(parents=True,mode=0o700)
labels=('local.atvloadly.agent','local.atvloadly.menubar','local.atvloadly.native.backend')
loaded=[];saved_agents=[];app_swapped=False;data_saved=False
native_plist=home/'Library/LaunchAgents/local.atvloadly.native.backend.plist'
native_before=native_plist.read_bytes() if native_plist.exists() else None
old_sibling=target.with_name('ATVLoadly.previous-'+str(time.time_ns())+'.app')
new_sibling=target.with_name('ATVLoadly.prepared-'+str(time.time_ns())+'.app')
def run(args,check=True): return subprocess.run(args,check=check,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def copy(src,dst):
 if src.is_dir(): shutil.copytree(src,dst,symlinks=False)
 else: dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
def stop_label(label):
 service=f'gui/{os.getuid()}/{label}'
 result=subprocess.run(['/bin/launchctl','print',service],capture_output=True,text=True)
 if result.returncode: return
 match=re.search(r'^\s*pid = (\d+)\s*$',result.stdout,re.M)
 run(['/bin/launchctl','bootout',service]);loaded.append(label)
 if match:
  pid=int(match.group(1));deadline=time.monotonic()+10
  while True:
   try:os.kill(pid,0)
   except ProcessLookupError:break
   if time.monotonic()>deadline:raise RuntimeError('A legacy process did not stop; refusing to copy live data.')
   time.sleep(.05)
def stop_new_ui():
 path=root/'updates/ui-pid'
 if not path.exists():return
 try:
  pid=int(path.read_text().strip())
  name=subprocess.check_output(['/bin/ps','-p',str(pid),'-o','comm='],text=True).strip()
  if name==str(target/'Contents/MacOS/ATVLoadly'):os.kill(pid,15)
 except (ValueError,ProcessLookupError,subprocess.CalledProcessError):pass
def stop_legacy_ui():
 info=target/'Contents/Info.plist'
 if not info.exists():return
 executable=plistlib.loads(info.read_bytes()).get('CFBundleExecutable')
 if not executable:return
 expected=str(target/'Contents/MacOS'/executable)
 for line in processes.splitlines():
  fields=line.strip().split(None,1)
  if len(fields)!=2 or fields[1]!=expected:continue
  pid=int(fields[0]);os.kill(pid,15);deadline=time.monotonic()+10
  while True:
   try:os.kill(pid,0)
   except ProcessLookupError:break
   if time.monotonic()>deadline:raise RuntimeError('Legacy menu app did not stop; cutover postponed.')
   time.sleep(.05)
items=[(root/'data','data'),(root/'config.yaml','config.yaml'),(home/'.config/PlumeImpactor','plume'),(home/'.config/atvloadly/lockdown','lockdown')]
try:
 target.parent.mkdir(parents=True,exist_ok=True)
 run(['/usr/bin/ditto','--norsrc','--noextattr',str(source),str(new_sibling)])
 run(['/usr/bin/codesign','--verify','--deep','--strict',str(new_sibling)])
 for label in labels:stop_label(label)
 stop_legacy_ui()
 if target.exists():run(['/usr/bin/ditto','--norsrc','--noextattr',str(target),str(backup/'ATVLoadly.app')])
 for src,name in items:
  if src.exists():copy(src,backup/name)
 db=backup/'data/app.db'
 connection=sqlite3.connect(f'file:{db}?mode=ro',uri=True)
 if connection.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Backup database integrity check failed.')
 before_count=connection.execute('SELECT COUNT(*) FROM installed_apps').fetchone()[0];connection.close()
 manifest=[]
 for file in backup.rglob('*'):
  if file.is_file() and not file.is_symlink():manifest.append({'path':str(file.relative_to(backup)),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
 (backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
 for entry in manifest:
  if hashlib.sha256((backup/entry['path']).read_bytes()).hexdigest()!=entry['sha256']:raise RuntimeError('Backup hash validation failed.')
 data_saved=True
 for label in ('local.atvloadly.agent','local.atvloadly.menubar'):
  plist=home/'Library/LaunchAgents'/(label+'.plist')
  if plist.exists():
   stored=backup/(label+'.plist');shutil.move(plist,stored);saved_agents.append((stored,plist))
 if target.exists():target.rename(old_sibling)
 new_sibling.rename(target);app_swapped=True
 run(['/usr/bin/open',str(target)])
 deadline=time.monotonic()+20;healthy=False
 while time.monotonic()<deadline:
  try:
   with urllib.request.urlopen('http://127.0.0.1:5533/native/ready',timeout=1) as response:new=json.load(response)
   if new.get('status')=='ready' and new.get('counts',{}).get('installed_apps')==before_count and not new.get('probation'):
    healthy=True;break
  except (OSError,ValueError):pass
  time.sleep(.2)
 if not healthy:raise RuntimeError('Replacement did not pass DB-backed readiness and record-count checks.')
 (backup/'cutover-result.json').write_text(json.dumps({'healthy':True,'installed_app_records':before_count,'time':time.time()},indent=2))
 print('Native application installed and backend health verified.')
 print('Reversible migration backup:',backup)
except Exception:
 if not app_swapped and old_sibling.exists() and not target.exists():old_sibling.rename(target)
 if app_swapped:
  run(['/bin/launchctl','bootout',f'gui/{os.getuid()}/local.atvloadly.native.backend'],check=False)
  run([str(target/'Contents/MacOS/ATVLoadly'),'--unregister-login'],check=False)
  stop_new_ui()
  if native_before is None:native_plist.unlink(missing_ok=True)
  else:native_plist.write_bytes(native_before)
  target.rename(target.with_name('ATVLoadly.failed-'+str(time.time_ns())+'.app'))
  if old_sibling.exists():old_sibling.rename(target)
  if data_saved:
   for dst,name in items:
    src=backup/name
    if not src.exists():continue
    if dst.exists() or dst.is_symlink():dst.rename(dst.with_name(dst.name+'.failed-'+str(time.time_ns())))
    copy(src,dst)
 for stored,plist in saved_agents:
  if stored.exists():shutil.copy2(stored,plist)
 for label in loaded:
  plist=home/'Library/LaunchAgents'/(label+'.plist')
  if plist.exists():run(['/bin/launchctl','bootstrap',f'gui/{os.getuid()}',str(plist)],check=False)
 if target.exists():run(['/usr/bin/open',str(target)],check=False)
 print('Cutover failed; previous application/service/data restoration attempted. Backup:',backup)
 raise
