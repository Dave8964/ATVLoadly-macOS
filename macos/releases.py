"""Select stable upstream versions using strict SemVer ordering."""
import json, re, sys

def version(tag):
    match = re.fullmatch(r'v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', tag)
    return tuple(map(int, match.groups())) if match else None

def latest(releases):
    eligible = [r for r in releases if not r.get('draft') and not r.get('prerelease') and version(r.get('tag_name', '')) is not None]
    if not eligible:
        raise ValueError('No stable upstream releases; refusing to infer a version')
    return max(eligible, key=lambda r: version(r['tag_name']))['tag_name']

if __name__ == '__main__':
    print(latest(json.load(sys.stdin)))
