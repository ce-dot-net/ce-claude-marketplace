#!/bin/bash

# ACE SessionStart Hook
# Injects ACE system instructions at session start

cat <<'EOF'
{
  "continue": true,
  "additionalContext": "🚨 ACE SYSTEM ACTIVE: The ace-playbook-retrieval skill (BEFORE work) and ace-learning skill (AFTER work) will auto-trigger based on task keywords. Trigger keywords: implement, build, create, add, develop, write, update, modify, change, edit, enhance, extend, revise, fix, debug, troubleshoot, resolve, diagnose, refactor, optimize, improve, restructure, integrate, connect, setup, configure, install, architect, design, plan, test, verify, validate, deploy, migrate, upgrade. CHECK EVERY user message for these trigger words and invoke skills accordingly."
}
EOF
