---
title: ACE Bootstrap
description: Initialize ACE playbook from codebase
---

1. **Bootstrap Playbook**
   This analyzes your codebase to create initial patterns.
   Replace `MODE` with one of: `hybrid` (recommended), `local-files`, `git-history`, or `docs-only`.
   ```bash
   .agent/ace/adapter.py bootstrap "MODE"
   ```
