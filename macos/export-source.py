"""Export complete patched ATVLoadly source, excluding build caches and private data."""
import pathlib, subprocess, sys, tarfile
root=pathlib.Path(sys.argv[1]).resolve();output=pathlib.Path(sys.argv[2]).resolve()
tracked=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
paths={p for p in tracked if p and (root/p).is_file()}
for folder in ('macos','internal/nativeupdate'):
 for p in (root/folder).rglob('*'):
  if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.rs','.py','.sh','.swift','.go','.mod','.sum','.md','.patch','.txt'):
   paths.add(p.relative_to(root).as_posix())
for p in (root/'internal').rglob('macos*test.go'): paths.add(p.relative_to(root).as_posix())
p=root/'internal/manager/device_manager_mdns_macos_test.go';paths.add(p.relative_to(root).as_posix())
epoch=int(subprocess.check_output(['git','show','-s','--format=%ct','HEAD'],cwd=root))
def normalized(info):
 info.uid=info.gid=0;info.uname=info.gname='root';info.mtime=epoch;return info
with tarfile.open(output,'w:gz') as archive:
 for rel in sorted(paths): archive.add(root/rel,arcname='ATVLoadly-macOS/'+rel,recursive=False,filter=normalized)
