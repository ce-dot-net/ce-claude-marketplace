#!/usr/bin/env python3
"""Probe: the 8.1.3 task-outcome rule (current tree) vs an older rule (a git ref) over local Claude Code transcripts.

COUNTS ONLY: never prints prompts, file contents, commands or paths. Families are printed with every token that is
not a plain lowercase word replaced by '*'.

  python3 tests/probe_success_rule.py --days 10 [--old-ref ea5dafb] [--root ~/.claude/projects]

A turn = the main-transcript lines from one user prompt to the next (sidechains and subagent files skipped); its tool
calls go through each rule's task_outcome exactly as the Stop hook's transcript path builds them. Old action stats
come from the transcript (complete inputs), so they show the old 60-char cut, not the accumulator caps.
"""
import argparse
import collections
import json
import re
import subprocess
import sys
import time
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / 'plugins/ace/shared-hooks'
SRC = 'plugins/ace/shared-hooks/ace_after_task.py'
_WORD = re.compile(r'-?[a-z][a-z0-9-]{0,15}$')


def load_new():
    sys.path.insert(0, str(HOOKS))
    import ace_after_task
    return ace_after_task


def load_old(ref):
    code = subprocess.run(['git', '-C', str(REPO), 'show', '%s:%s' % (ref, SRC)], capture_output=True, text=True,
                          check=True).stdout
    mod = types.ModuleType('ace_after_task_old')
    mod.__file__ = str(HOOKS / 'ace_after_task_old.py')
    exec(compile(code, mod.__file__, 'exec'), mod.__dict__)
    return mod


def safe_family(fam, verbs=()):
    if fam.startswith('mcp__'):  # only the matched write verb, never the server or tool name
        act = re.sub(r'([a-z])([A-Z])', r'\1_\2', fam.rsplit('__', 1)[-1]).lower()
        return 'mcp ' + next((w for w in re.split(r'[^a-z0-9]+', act) if w in verbs), '*')
    return ' '.join(w if _WORD.match(w) else '*' for w in fam.split()) or '(none)'


def is_prompt(e):
    m = e.get('message') if isinstance(e, dict) else None
    if not isinstance(m, dict) or m.get('role') != 'user' or e.get('isSidechain'):
        return False
    c = m.get('content')
    return isinstance(c, str) or (isinstance(c, list) and not any(
        isinstance(b, dict) and b.get('type') == 'tool_result' for b in c))


def turns(path):
    """(day, [raw lines]) per turn of one transcript."""
    cur, day = None, None
    with open(path, 'rb') as f:
        for raw in f:
            line = raw.decode('utf-8', 'replace')
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if not isinstance(e, dict) or e.get('isSidechain'):
                continue
            if is_prompt(e):
                if cur:
                    yield day, cur
                cur, day = [], str(e.get('timestamp') or '')[:10]
            elif cur is not None:
                cur.append(line)
    if cur:
        yield day, cur


def unrecovered_decisive(new, tools):
    """Indexes of the failed decisive steps no later ok step with the same key recovers (the new rule)."""
    steps = []
    for name, tin_json, tresp_json, *_ in tools:
        tin, resp = json.loads(tin_json or '{}'), json.loads(tresp_json or '{}')
        tin = tin if isinstance(tin, dict) else {}
        if name == 'Bash':
            fam, dec = new.bash_step(tin.get('command'))
            key = 'Bash:' + fam
        else:
            key, dec = name, name in new.DECISIVE_TOOLS or new.mcp_writes(name)
        steps.append((new._step_status(name, tin, resp), key, dec, tin))
    return [(i, s) for i, s in enumerate(steps) if s[0] == 'failed' and s[2]
            and not any(t[0] == 'ok' and t[1] == s[1] for t in steps[i + 1:])]


def why(old, new, tools, i, step):
    name = tools[i][0]
    if name.startswith('mcp__'):
        return 'SF4 mcp write', name
    cmd = step[3].get('command') or ''
    fam = new.command_family(cmd)
    old_fam = old.command_family(cmd)
    old_ro = old_fam in old.READ_ONLY_BASH
    resp = json.loads(tools[i][2] or '{}')
    if old._step_status(name, step[3], resp) == 'ok' or old_ro:
        pipe = len(new._split_top(new._split_top(cmd, new._CHAIN)[-1], ('|',))) > 1
        return ('MF2 pipeline last stage' if pipe else 'MF1 chain last non-read-only'), fam
    return 'SF3 finer family', fam


def bash_action_stats(old, new, tools, acc):
    for name, tin_json, *_ in tools:
        if name != 'Bash':
            continue
        tin = json.loads(tin_json or '{}')
        tin = tin if isinstance(tin, dict) else {}
        a_old, a_new = old.summarize_tool_action('Bash', tin), new.summarize_tool_action('Bash', tin)
        body = a_old[len('Ran: '):] if a_old.startswith('Ran: ') else a_old
        acc['bash_steps'] += 1
        acc['old_empty'] += body.strip() in ('', '...')
        acc['old_cut'] += body.endswith('...')
        acc['new_unknown'] += a_new.startswith('unknown')
        acc['new_cut'] += a_new.endswith('...')


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=10)
    ap.add_argument('--old-ref', default='ea5dafb', help='git ref of the old rule (ea5dafb = 8.1.3 before the review)')
    ap.add_argument('--root', default=str(Path.home() / '.claude' / 'projects'))
    a = ap.parse_args(argv)
    new, old = load_new(), load_old(a.old_ref)
    since = time.time() - a.days * 86400
    cutoff_day = time.strftime('%Y-%m-%d', time.gmtime(since))
    per_day = collections.defaultdict(lambda: [0, 0, 0])  # turns, old false, new false
    flips, back, fams, acc = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
    unreadable = 0
    for p in Path(a.root).expanduser().glob('*/*.jsonl'):
        try:
            if p.stat().st_mtime < since:
                continue
            for day, lines in turns(p):
                if day < cutoff_day:
                    continue
                tools = new._tools_from_transcript_lines(lines, None)
                if not tools:
                    continue
                o, n = old.task_outcome(tools)[0], new.task_outcome(tools)[0]
                d = per_day[day]
                d[0] += 1
                d[1] += not o
                d[2] += not n
                bash_action_stats(old, new, tools, acc)
                if o and not n:
                    bad = unrecovered_decisive(new, tools)
                    if bad:
                        reason, fam = why(old, new, tools, *bad[0])
                    else:
                        reason, fam = 'interrupted last step', ''
                    flips[reason] += 1
                    fams[safe_family(fam, new.MCP_WRITE_VERBS)] += 1
                elif n and not o:
                    back['old false -> new true'] += 1
        except Exception:
            unreadable += 1
    print('day         turns  old_false  new_false')
    tot = [0, 0, 0]
    for day in sorted(per_day):
        t, of, nf = per_day[day]
        tot = [tot[0] + t, tot[1] + of, tot[2] + nf]
        print('%-10s  %5d  %9d  %9d' % (day, t, of, nf))
    t = tot[0] or 1
    print('total       %5d  %9d  %9d   success old %.1f%%  new %.1f%%' % (tot[0], tot[1], tot[2], 100 * (t - tot[1]) / t,
                                                                         100 * (t - tot[2]) / t))
    print('flipped true -> false by fix:', dict(flips.most_common()))
    print('flipped false -> true:', sum(back.values()))
    print('top reclassified families:', fams.most_common(10))
    b = acc['bash_steps'] or 1
    print('bash actions: %d steps; old empty %.1f%% cut %.1f%%; new unknown %.1f%% cut %.1f%%'
          % (acc['bash_steps'], 100 * acc['old_empty'] / b, 100 * acc['old_cut'] / b, 100 * acc['new_unknown'] / b,
             100 * acc['new_cut'] / b))
    if unreadable:
        print('unreadable transcripts:', unreadable)


if __name__ == '__main__':
    main()
