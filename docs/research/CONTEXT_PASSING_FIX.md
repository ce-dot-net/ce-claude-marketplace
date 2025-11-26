# Context Passing Fix - Environment Variables Pattern ✅

**Date**: 2025-11-18
**Status**: Complete and Tested

---

## 🎯 Problem Summary

Initial "simplification" removed `--org` and `--project` flags but didn't pass context via subprocess environment, breaking all Python hooks.

---

## 💡 Solution: Environment Variables Pattern

Pass context via **subprocess environment variables** instead of CLI flags:

```python
# Build environment with context
env = os.environ.copy()
if org:
    env['ACE_ORG_ID'] = org
if project:
    env['ACE_PROJECT_ID'] = project

# Pass to subprocess
result = subprocess.run(
    ['ce-ace', 'search', '--stdin', '--json'],
    env=env,  # ← Context passed here
    ...
)
```

---

## 📐 Architecture Understanding

### The 3-Layer Chain (NOT Over-Engineered)

```
┌─────────────────────────────────────────────────────┐
│ Layer 1: Bash Wrappers                             │
│ - Plugin isolation                                  │
│ - Path resolution to shared hooks                  │
│ - Python environment setup (uv run)                │
└─────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────┐
│ Layer 2: Python Hooks                              │
│ - Parse JSON events from Claude Code               │
│ - Read context from .claude/settings.json          │
│ - Build subprocess environment                      │
│ - Format output (domains, bullets, emoji)          │
└─────────────────────────────────────────────────────┘
                    ↓ (env vars)
┌─────────────────────────────────────────────────────┐
│ Layer 3: ce-ace CLI Subprocess                     │
│ - Read ACE_ORG_ID, ACE_PROJECT_ID from env         │
│ - Fetch server config (top_k, threshold)           │
│ - Communicate with ACE Server                       │
│ - Return JSON response                              │
└─────────────────────────────────────────────────────┘
```

**Each layer has a distinct purpose** - the architecture follows the cc-boilerplate-v2 pattern exactly!

---

## 📝 Files Fixed

### 1. `shared-hooks/utils/ace_cli.py`

**run_search()**:
```python
def run_search(query: str, org: str = None, project: str = None):
    """Context passed via environment variables"""
    env = os.environ.copy()
    if org:
        env['ACE_ORG_ID'] = org
    if project:
        env['ACE_PROJECT_ID'] = project

    result = subprocess.run(
        ['ce-ace', 'search', '--stdin', '--json'],
        env=env,  # ← Pass context
        ...
    )
```

**run_learn()** and **run_status()** - Same pattern.

### 2. `shared-hooks/ace_before_task.py`

**Before (BROKEN)**:
```python
# ❌ Context read but not passed to subprocess
patterns_response = run_search(query=user_prompt)
```

**After (FIXED)**:
```python
# ✅ Context passed to subprocess environment
patterns_response = run_search(
    query=user_prompt,
    org=context['org'],
    project=context['project']
)
```

### 3. `shared-hooks/ace_after_task.py`

**Before (BROKEN)**:
```python
# ❌ Calling subprocess without context
result = subprocess.run(['ce-ace', 'learn', '--stdin', '--json'], ...)
```

**After (FIXED)**:
```python
# ✅ Build environment with context
env = os.environ.copy()
if context['org']:
    env['ACE_ORG_ID'] = context['org']
if context['project']:
    env['ACE_PROJECT_ID'] = context['project']

result = subprocess.run(
    ['ce-ace', 'learn', '--stdin', '--json'],
    env=env,  # ← Pass context
    ...
)
```

### 4. `shared-hooks/ace_task_complete.py`

Same fix as `ace_after_task.py`.

### 5. `plugins/ace/tests/test_ace_cli.py`

Updated tests to verify environment passing:

```python
def test_run_search_success():
    """Test successful search call with context passed via environment"""
    with patch('subprocess.run', return_value=mock_result) as mock_run:
        result = run_search('test query', org='org_123', project='prj_456')

        # Verify env vars passed
        args, kwargs = mock_run.call_args
        assert kwargs['env']['ACE_ORG_ID'] == 'org_123'
        assert kwargs['env']['ACE_PROJECT_ID'] == 'prj_456'
```

All tests pass ✅

---

## 🧪 Verification

### Test Results

**Unit Tests**:
```bash
$ python3 plugins/ace/tests/test_ace_cli.py
✅ test_run_search_success passed
✅ test_run_search_failure passed
✅ test_run_search_timeout passed
✅ test_run_search_invalid_json passed
✅ test_run_learn_success passed
✅ test_run_learn_failure passed
✅ test_run_status_success passed

✅ All tests passed!
```

**Integration Test**:
```bash
$ echo '{"prompt": "implement JWT authentication"}' | python3 shared-hooks/ace_before_task.py
✅ [ACE] Found 7 relevant bullets
   Domains: general, jwt-token-validation-fix
   • [jwt-token-validation-fix] JWT authentication debugging workflow... (+3)
   • [general] JWT implementation workflow... (+5)
   ... and 4 more bullets
```

**Result**: Hook correctly uses project-specific context! 🎉

---

## 🔑 Key Learnings

### 1. Architecture is Well-Designed

The 3-layer chain (Bash → Python → CLI) follows the cc-boilerplate-v2 pattern exactly:
- ✅ Each layer has a distinct purpose
- ✅ Separation of concerns
- ✅ NOT over-engineered

### 2. Environment Variables = Best Practice

For Python subprocess calls, context should be passed via environment:
- ✅ Cleaner than flags (`env=env` vs `--org`, `--project`)
- ✅ Matches ACE Research Paper pattern
- ✅ CLI reads from env vars automatically

### 3. Bash Commands Already Correct

Slash commands in `plugins/ace/commands/*.md` were already using the correct pattern:
```bash
export ACE_ORG_ID="..."
export ACE_PROJECT_ID="..."
ce-ace search "$*"
```

---

## 📊 Final Summary

**What Was Fixed**:
- ❌ Removed: `--org` and `--project` flags (correct)
- ❌ Missing: Environment variable passing (bug)
- ✅ Added: `env=env` to subprocess calls (fix)

**Files Changed**: 5
- `shared-hooks/utils/ace_cli.py` (3 functions)
- `shared-hooks/ace_before_task.py` (1 call site)
- `shared-hooks/ace_after_task.py` (1 subprocess call)
- `shared-hooks/ace_task_complete.py` (1 subprocess call)
- `plugins/ace/tests/test_ace_cli.py` (3 test cases)

**Lines Changed**: ~30 lines (adding env parameter passing)

**Result**:
- ✅ No CLI flags passed
- ✅ Context passed via environment
- ✅ CLI reads server config automatically
- ✅ Project-specific configuration works
- ✅ All tests pass
- ✅ End-to-end verified

---

## 🎓 Lessons Learned

1. **Test end-to-end** - Unit tests passed but integration was broken
2. **Understand the chain** - Each layer has a purpose
3. **Environment variables** - Correct pattern for subprocess context
4. **Don't assume simplification** - "Removing parameters" ≠ "Simplifying correctly"

---

**Status**: ✅ Production Ready
**Verification**: All tests pass, hook works with real ce-ace CLI
**Architecture**: Follows cc-boilerplate-v2 pattern exactly
