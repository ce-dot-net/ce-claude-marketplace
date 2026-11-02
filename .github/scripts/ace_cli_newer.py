#!/usr/bin/env python3
"""ace-cli-watch: `ace_cli_newer.py LATEST PIN` prints yes only when LATEST is a plain x.y.z strictly
greater than PIN (a rolled-back npm tag, a prerelease or anything else prints no)."""
import re
import sys


def newer(latest, pin):
    ok = re.compile(r"\d+\.\d+\.\d+")
    if not (ok.fullmatch(latest or "") and ok.fullmatch(pin or "")):
        return False
    return tuple(map(int, latest.split("."))) > tuple(map(int, pin.split(".")))


if __name__ == "__main__":
    print("yes" if newer(*sys.argv[1:3]) else "no")
