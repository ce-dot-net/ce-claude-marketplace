---
title: ACE Install
description: Install or Update the ACE Antigravity Integration
---

1.  **Silent Install**
    Clone the codebase and install integration files.
    // turbo
    ```bash
    # 1. Clone to temp
    git clone -q https://github.com/ce-dot-net/ce-claude-marketplace.git .ace_temp_install

    # 2. Create directories
    mkdir -p .agent/ace .agent/workflows .antigravity

    # 3. Install Files
    cp -r .ace_temp_install/.agent/ace/* .agent/ace/
    cp -r .ace_temp_install/.agent/workflows/* .agent/workflows/
    cp -r .ace_temp_install/.antigravity/* .antigravity/

    # 4. Remove temporary clone
    rm -rf .ace_temp_install
    ```

2.  **Configuration Check**
    Creating a configuration file if one doesn't exist.
    // turbo
    ```bash
    if [ ! -f .antigravity/ace.json ]; then
      echo '{ "ace": { "org_id": "", "project_id": "" } }' > .antigravity/ace.json
      echo "✅ Created .antigravity/ace.json"
    else
      echo "ℹ️  .antigravity/ace.json already exists"
    fi
    ```

3.  **Completion**
    Installation is complete.
    > [!IMPORTANT]
    > Please open **[.antigravity/ace.json](file:///.antigravity/ace.json)** and add your `org_id` and `project_id` to finish the setup.
