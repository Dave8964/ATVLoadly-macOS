"""Select upstream releases and avoid rebuilding an unchanged integration."""
import json, os, pathlib, sys, hashlib, subprocess
from releases import latest
upstream_pages=json.loads(pathlib.Path(sys.argv[1]).read_text())
release_pages=json.loads(pathlib.Path(sys.argv[2]).read_text())
upstream=[r for page in upstream_pages for r in page]
published=[r for page in release_pages for r in page]
tag=latest(upstream)
sha=os.environ['GITHUB_SHA'];run=os.environ['GITHUB_RUN_NUMBER']
fingerprint=hashlib.sha256(subprocess.check_output(['git','ls-tree','-r','HEAD','--','macos','build.sh','.github/workflows'])).hexdigest()
markers=f'Upstream-Version: {tag}\nIntegration-Fingerprint: {fingerprint}'
qualified=os.environ.get('QUALIFIED_RELEASES')=='true'
changed=not any(not r.get('draft') and markers in (r.get('body') or '') and (not qualified or not r.get('prerelease')) for r in published)
release_tag=f'macos-{tag}-'+(('build.' if qualified else 'candidate.')+run)
with open(os.environ['GITHUB_OUTPUT'],'a') as f:
 f.write(f'upstream={tag}\ntag={release_tag}\nchanged={str(changed).lower()}\n')
release=next(r for r in upstream if r['tag_name']==tag)
notes=f"Official upstream release: https://github.com/bitxeno/atvloadly/releases/tag/{tag}\n\n"+(release.get('body') or '')+f'\n\n{markers}\nIntegration-Commit: {sha}\n'
pathlib.Path(sys.argv[3]).write_text(notes)
print(f'Upstream {tag}; build needed: {changed}; production qualification: {qualified}')
