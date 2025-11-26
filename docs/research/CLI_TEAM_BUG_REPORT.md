# CLI Team Bug Report - Exact Reproduction

**Reported by**: ACE Plugin Team
**Date**: 2025-11-18
**CLI Version**: ce-ace@1.0.4

---

## Bug 2: --org and --project Flags Are Ignored

### Exact Command
```bash
ce-ace --org "org_34fYIlitYk4nyFuTvtsAzA6uUJF" --project "prj_d3a244129d62c198" status
```

### Environment State
```bash
# These env vars ARE set in the shell
ACE_ORG_ID=org_34fYIlitYk4nyFuTvtsAzA6uUJF
ACE_PROJECT_ID=prj_d3a244129d62c198
```

### Full Output
```
- Fetching playbook status...
✅ Loaded config from: /Users/ptsafaridis/.config/ace/config.json
   Multi-org: 3 organization(s) configured
✅ Using ACE_PROJECT_ID from environment  <--- 🐛 BUG: Should use CLI flags!
✅ Using ACE_ORG_ID from environment      <--- 🐛 BUG: Should use CLI flags!

📋 Final Configuration:
   serverUrl: https://ace-api.code-engine.app
   projectId: prj_d3a244129d62c198
   organization: ce-dot-net (org_34fYIlitYk4nyFuTvtsAzA6uUJF)

✔ Status retrieved
📊 Playbook Status
ℹ   Total Bullets:       0
```

### The Problem
- User explicitly passes `--org` and `--project` flags
- CLI output says "Using ACE_PROJECT_ID from **environment**"
- Flags are **completely ignored**, env vars take precedence

### Expected Behavior (per docs)
```
Tier 1 (Highest Priority):
  CLI Flags: --org <org_id> --project <project_id>
    ↓
Tier 2:
  Environment Variables: ACE_ORG_ID, ACE_PROJECT_ID
```

### Actual Behavior
```
Environment variables override CLI flags (opposite of documented behavior)
```

### Impact
- Users cannot use flags to override environment
- Documented Tier 1 precedence doesn't work
- Integration guides are incorrect

### Root Cause Hypothesis
Looking at your code mention (cli.ts:176-177), the preAction hook captures flags but might not be setting them with higher precedence than env vars in the context resolver.

**Check**: Does context resolver check `process.env.ACE_ORG_ID` BEFORE checking captured flags?

---

## Bug 3: --server-url Flag Ignored in config validate

### Exact Command
```bash
ce-ace config validate \
  --server-url "https://ace-api.code-engine.app" \
  --api-token "ace_test_token_12345"
```

### Environment State
```bash
# These are NOT set
echo ${ACE_SERVER_URL:-NOT_SET}  # NOT_SET
echo ${ACE_API_TOKEN:-NOT_SET}   # NOT_SET
```

### Full Output
```
❌ Error: Server URL required. Use --server-url or set ACE_SERVER_URL
```

### The Problem
- User passes `--server-url` flag as instructed
- CLI says "Server URL required. Use --server-url" 🤦
- The error message tells user to do exactly what they're already doing!

### Workaround That Works
```bash
export ACE_SERVER_URL="https://ace-api.code-engine.app"
export ACE_API_TOKEN="ace_test_token_12345"
ce-ace config validate --json

# Output:
{"valid":false,"error":"Invalid token"}  <--- ✅ Works! No "Server URL required" error
```

### Root Cause Hypothesis
Looking at your code mention (config.ts:434), the flag IS registered with fallback, but the validation might be checking `process.env.ACE_SERVER_URL` BEFORE checking the captured flag value.

**Check**:
1. Where does `config validate` read server URL from?
2. Is it checking flags before env vars?
3. Is the flag value being passed to the validation function?

---

## Additional Context: Bug 1 Still Needs Investigation

### Issue
Plain text output shows 0 bullets, JSON shows correct count:

```bash
# Plain text (WRONG)
ce-ace status
# Output: Total Bullets: 0

# JSON (CORRECT)
ce-ace status --json
# Output: "total_patterns": 70
```

### Question for CLI Team
- Is there a formatter bug in plain text output?
- Are there separate code paths for JSON vs plain text?
- Can you verify playbook fetch is the same for both formats?

---

## Testing Environment

**OS**: macOS Darwin 25.1.0
**Shell**: zsh
**Node**: v23.3.0
**CLI Version**: 1.0.4
**Config**: Multi-org mode (3 organizations)

**Config Location**: ~/.config/ace/config.json
**Project Settings**: .claude/settings.json (with orgId + projectId)

---

## Next Steps

1. **For Bug 2**: Check context resolver precedence order
2. **For Bug 3**: Check where config validate reads serverUrl from
3. **For Bug 1**: Compare plain text vs JSON output code paths
4. Consider adding integration tests that verify:
   - CLI flags override env vars (Tier 1 > Tier 2)
   - Flags are actually used, not just captured
   - Output formats produce consistent results

Let us know if you need more details or access to our test environment!
