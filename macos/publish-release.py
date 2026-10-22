"""Publish by release ID only after every draft asset has a matching digest."""
import hashlib,json,os,pathlib,re,subprocess,sys,time,urllib.parse


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
    return next((release for page in pages for release in page if release['tag_name']==tag),None)


def retry(call,errors=(subprocess.CalledProcessError,)):
    for delay in (0,1,2,4,8,16):
        if delay:time.sleep(delay)
        try:return call()
        except errors:
            if delay==16:raise


def main():
    tag=sys.argv[1];directory=pathlib.Path(sys.argv[2]).resolve()
    if not re.fullmatch(r'macos-v\d+\.\d+\.\d+-(candidate|build)\.\d+',tag):raise ValueError('Invalid release tag')
    sha=os.environ.get('RELEASE_SOURCE_SHA',os.environ.get('GITHUB_SHA',''))
    if not re.fullmatch(r'[0-9a-fA-F]{40}',sha):raise ValueError('Exact integration commit required')
    repo=os.environ['GITHUB_REPOSITORY'];qualified=os.environ.get('QUALIFIED_RELEASES')=='true'
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError('Invalid repository')
    def gh(*args):return subprocess.run(['gh',*args],check=True,capture_output=True,text=True).stdout
    def api(endpoint,*args):return json.loads(gh('api',endpoint,*args))
    existing=os.environ.get('EXISTING_RELEASE_ID','')
    if existing:
        if not existing.isdigit():raise ValueError('Invalid draft release ID')
        release=retry(lambda:api(f'repos/{repo}/releases/{existing}'))
    else:
        release=find_release(api(f'repos/{repo}/releases?per_page=100','--paginate','--slurp'),tag)
    if release is None:
        title=f'ATVLoadly macOS {tag}'+('' if qualified else ' — test candidate')
        # Retain the creation response. A fresh draft need not be visible in a listing yet.
        release=api(f'repos/{repo}/releases','--method','POST','-f',f'tag_name={tag}',
                    '-f',f'target_commitish={sha}','-f',f'name={title}','-F','draft=true',
                    '-f','body='+(directory/'release-body.md').read_text())
    if release.get('tag_name')!=tag or not release.get('draft'):
        raise ValueError('Refusing to replace a published or unrelated release')
    release_id=int(release['id'])
    endpoint=f'repos/{repo}/releases/{release_id}'
    def get():return retry(lambda:api(endpoint))
    files=sorted(p for p in directory.iterdir() if p.is_file() and not p.name.startswith('.'))
    if not files:raise ValueError('No release artifacts')
    for file in files:
        expected='sha256:'+hashlib.sha256(file.read_bytes()).hexdigest()
        for attempt in range(3):
            state=get()
            if not state.get('draft'):raise ValueError('Draft was published before asset validation')
            asset=next((a for a in state['assets'] if a['name']==file.name),None)
            if asset and asset.get('digest')==expected and asset.get('size')==file.stat().st_size:break
            if asset:gh('api',f"repos/{repo}/releases/assets/{int(asset['id'])}",'--method','DELETE')
            upload=f'https://uploads.github.com/repos/{repo}/releases/{release_id}/assets?name='+urllib.parse.quote(file.name,safe='')
            try:
                result=api(upload,'--method','POST','--header','Content-Type: application/octet-stream','--input',str(file))
                if result.get('digest')==expected and result.get('size')==file.stat().st_size:break
                raise ValueError('Uploaded asset digest mismatch: '+file.name)
            except (subprocess.CalledProcessError,ValueError):
                if attempt==2:raise
                time.sleep(2)
    retry(lambda:verify_assets(directory,get()['assets']),errors=(subprocess.CalledProcessError,ValueError))
    result=api(endpoint,'--method','PATCH','-f',f'target_commitish={sha}','-F','draft=false',
               '-F','prerelease='+str(not qualified).lower(),'-f','make_latest='+str(qualified).lower())
    if result.get('draft') is not False or result.get('prerelease')!=(not qualified):
        raise ValueError('Publication state was not confirmed')
    print(f'Published verified {"stable" if qualified else "test"} release: https://github.com/{repo}/releases/tag/{tag}')


if __name__=='__main__':
    try:main()
    except subprocess.CalledProcessError as error:
        print(error.stderr.strip(),file=sys.stderr)
        raise SystemExit(1)
