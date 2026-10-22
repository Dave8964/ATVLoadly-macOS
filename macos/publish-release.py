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

def find_release(pages,tag):
    # Drafts may have no published Git tag, so the by-tag endpoint is unsuitable.
    return next((release for page in pages for release in page if release['tag_name']==tag),None)

def main():
    tag=sys.argv[1];directory=pathlib.Path(sys.argv[2]).resolve()
    if not re.fullmatch(r'macos-v\d+\.\d+\.\d+-(candidate|build)\.\d+',tag):raise ValueError('Invalid release tag')
    sha=os.environ['GITHUB_SHA']
    if not re.fullmatch(r'[0-9a-fA-F]{40}',sha):raise ValueError('Exact integration commit required')
    repo=os.environ['GITHUB_REPOSITORY'];qualified=os.environ.get('QUALIFIED_RELEASES')=='true'
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError('Invalid repository')
    def gh(*args):return subprocess.run(['gh',*args],check=True,capture_output=True,text=True).stdout
    def get():return find_release(json.loads(gh('api','--paginate','--slurp',f'repos/{repo}/releases?per_page=100')),tag)
    release=get()
    if release is None:
        title=f'ATVLoadly macOS {tag}'+('' if qualified else ' — test candidate')
        gh('release','create',tag,'--repo',repo,'--draft','--target',sha,'--title',title,'--notes-file',str(directory/'release-body.md'))
        release=get()
        if release is None:raise ValueError('Created draft release could not be resolved')
    if not release.get('draft'):raise ValueError('Refusing to replace an already published release')
    files=sorted(str(p) for p in directory.iterdir() if p.is_file() and not p.name.startswith('.'))
    for attempt in range(3):
        try:
            gh('release','upload',tag,'--repo',repo,'--clobber',*files)
            verify_assets(directory,json.loads(gh('api',f"repos/{repo}/releases/{release['id']}"))['assets'])
            break
        except (subprocess.CalledProcessError,ValueError):
            if attempt==2:raise
            time.sleep(2)
    args=['release','edit',tag,'--repo',repo,'--target',sha,'--draft=false']
    args+=['--prerelease=false','--latest'] if qualified else ['--prerelease','--latest=false']
    gh(*args)
    print(f'Published verified {"stable" if qualified else "test"} release: https://github.com/{repo}/releases/tag/{tag}')
if __name__=='__main__':main()
