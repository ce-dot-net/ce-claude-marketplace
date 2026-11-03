#!/usr/bin/env python3
"""ace-cli-watch pr job: the applied bump patch may change ONLY the pinned @ace-sdk/cli version (DESIGN §27).

Usage (repo root, patch applied to the work tree): verify_bump.py <old_pin> <new_version>
Compares every changed file against `git show HEAD:<file>` at JSON level; prints the violations, exit 1 on any.
Runs no package code. Lock rule: only the root entry's @ace-sdk/cli spec and node_modules/@ace-sdk/* entries may
change, each with an https registry.npmjs.org tarball, an sha512 integrity and no new install script.
"""
import json
import re
import subprocess
import sys

PKG = "plugins/ace/package.json"
LOCK = "plugins/ace/package-lock.json"
MANIFESTS = ("plugins/ace/.claude-plugin/plugin.json", "plugins/ace/.claude-plugin/plugin.template.json",
             ".claude-plugin/marketplace.json")
REGISTRY = "https://registry.npmjs.org/"


def verify(old, new, pin, latest):
    """old/new: {path: text} of the changed files. Returns a list of violations ([] = clean)."""
    errs = []
    for path in sorted(set(old) | set(new)):
        if path not in (PKG, LOCK) + MANIFESTS:
            errs.append("file outside the allow-list: " + path)
        elif old.get(path) is None or new.get(path) is None:
            errs.append("file added or removed: " + path)
    if errs:
        return errs
    if PKG in new:
        o, n = json.loads(old[PKG]), json.loads(new[PKG])
        o.setdefault("dependencies", {})["@ace-sdk/cli"] = latest
        if o != n or json.loads(old[PKG]).get("dependencies", {}).get("@ace-sdk/cli") != pin:
            errs.append(PKG + ": changes beyond the @ace-sdk/cli pin %s -> %s" % (pin, latest))
    for m in MANIFESTS:
        if m in new and old[m].replace("ace-cli >= " + pin, "ace-cli >= " + latest) != new[m]:
            errs.append(m + ": changes beyond 'ace-cli >= %s' -> %s" % (pin, latest))
    if LOCK in new:
        errs += _lock(json.loads(old[LOCK]), json.loads(new[LOCK]), latest)
    return errs


def _lock(o, n, latest):
    errs = []
    if {k: v for k, v in o.items() if k != "packages"} != {k: v for k, v in n.items() if k != "packages"}:
        errs.append(LOCK + ": top-level fields changed")
    op, np_ = o.get("packages", {}), n.get("packages", {})
    for key in sorted(set(op) | set(np_)):
        a, b = op.get(key), np_.get(key)
        if a == b:
            continue
        if key == "":
            want = json.loads(json.dumps(a))
            want.setdefault("dependencies", {})["@ace-sdk/cli"] = latest
            if want != b:
                errs.append(LOCK + ": root entry changes beyond the @ace-sdk/cli spec")
            continue
        if not re.fullmatch(r"node_modules/@ace-sdk/(cli|core)", key):
            errs.append(LOCK + ": entry outside @ace-sdk/cli|core changed: " + key)
            continue
        if b is None:
            continue  # a removed @ace-sdk entry installs nothing
        extra = sorted({"name", "link", "alias"} & set(b))
        if extra:
            errs.append(LOCK + ": %s carries %s (alias/link entries are refused)" % (key, extra))
        pkg = key[len("node_modules/"):]
        want = "%s%s/-/%s-%s.tgz" % (REGISTRY, pkg, pkg.split("/")[-1], b.get("version"))
        if b.get("resolved") != want or not str(b.get("integrity", "")).startswith("sha512-"):
            errs.append(LOCK + ": %s is not its own npm registry tarball (%s) with sha512 integrity" % (key, want))
        if b.get("hasInstallScript") and not (a or {}).get("hasInstallScript"):
            errs.append(LOCK + ": %s gained an install script" % key)
    return errs


def _git_show(path):
    p = subprocess.run(["git", "show", "HEAD:" + path], capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def main(argv):
    pin, latest = argv[1], argv[2]
    # porcelain + untracked-files=all: a NEW file (absent from HEAD) must reach verify(), which rejects it
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "-z"], capture_output=True,
                         text=True, check=True).stdout
    changed = [e[3:] for e in out.split("\0") if len(e) > 3]
    old = {p: _git_show(p) for p in changed}
    new = {}
    for p in changed:
        try:
            with open(p) as f:
                new[p] = f.read()
        except OSError:
            new[p] = None
    errs = verify(old, new, pin, latest)
    for e in errs:
        print("::error::" + e)
    return 1 if errs or not changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
