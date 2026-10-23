"""Select upstream's engine, with a reviewed override for the v0.7.3 candidate."""
import re
import sys


def select(version, dockerfile):
    match = re.search(r"PlumeImpactor/releases/download/([^/]+)/", dockerfile)
    if not match:
        raise ValueError("Upstream signing-engine tag was not found")
    tag = match.group(1)
    # Never downgrade a future upstream release to this compatibility candidate.
    if version == "v0.7.3" and tag == "v2.7.1-patch.3":
        return "v2.7.1-patch.4"
    return tag


if __name__ == "__main__":
    from pathlib import Path
    print(select(sys.argv[1], Path(sys.argv[2]).read_text()))
