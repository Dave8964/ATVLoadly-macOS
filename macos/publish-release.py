"""Publish only after every draft asset has a matching server-side digest."""
import hashlib,json,os,pathlib,re,subprocess,sys,time

def verify_assets(directory,assets):
    remote={item['name']:item for item in assets}
    files=sorted(p for p in directory.iterdir() if p.is_file() and not p.name.startswith('.'))
    if not files: raise ValueError('No release artifacts')
    for file in files:
        asset=remote.get(file.name)
        expected='sha256:'+hashlib.sha256(file.read_bytes()).hexdigest()
        if not asset or asset.get('digest')!=expected or asset.get('size')!=file.stat().st_size:
            raise ValueError('Draft asset integrity mismatch: '+file.name)
    return files

def main():
    tag=sys.argv[1];directory=pathlib.Path(sys.argv[2]).resolve()
    if not re.fullmatch(r'macos-v\d+\.\d+\.\d+-(candidate|build)\.\d+',tag):raise ValueError('Invalid release tag')
    repo=os.environ['GITHUB_REPOSITORY'];qualified=os.environ.get('QUALIFIED_RELEASES')=='true'
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError('Invalid repository')
    def gh(*args):return subprocess.run(['gh',*args],check=True,capture_output=True,text=True).stdout
    def get():return json.loads(gh('api',f'repos/{repo}/releases/tags/{tag}'))
    try:release=get()
    except subprocess.CalledProcessError as error:
        if 'HTTP 404' not in error.stderr:raise
        title=f'ATVLoadly macOS {tag}'+('' if qualified else ' — test candidate')
        gh('release','create',tag,'--repo',repo,'--draft','--title',title,'--notes-file',str(directory/'release-body.md'))
        release=get()
    if not release.get('draft'):raise ValueError('Refusing to replace an already published release')
    files=sorted(str(p) for p in directory.iterdir() if p.is_file() and not p.name.startswith('.'))
    for attempt in range(3):
        try:
            gh('release','upload',tag,'--repo',repo,'--clobber',*files)
            verify_assets(directory,get()['assets'])
            break
        except (subprocess.CalledProcessError,ValueError):
            if attempt==2:raise
            time.sleep(2)
    args=['release','edit',tag,'--repo',repo,'--draft=false']
    args+=['--prerelease=false','--latest'] if qualified else ['--prerelease','--latest=false']
    gh(*args)
    print(f'Published verified {"stable" if qualified else "test"} release: https://github.com/{repo}/releases/tag/{tag}')
if __name__=='__main__':main()
