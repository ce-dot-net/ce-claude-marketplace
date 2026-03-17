---
title: ACE Tune
description: Tune ACE project configuration
---

1. **View Current Config**
   ```bash
   .agent/ace/adapter.py tune --show
   ```

2. **Adjust Settings** (Example)
   Lower search threshold for broader matches:
   ```bash
   .agent/ace/adapter.py tune --constitution-threshold 0.4
   ```

3. **Reset to Defaults** (if needed)
   ```bash
   .agent/ace/adapter.py tune --reset
   ```
