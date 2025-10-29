#!/bin/bash
# ACE Prompt Enforcement - Runs on EVERY UserPromptSubmit
# Ensures ACE skills are enforced on every single prompt in an active session

# Read from stdin to get hook input (required for proper hook operation)
read -r HOOK_INPUT

# Output gets added to Claude's context for THIS specific prompt
cat << 'ENFORCEMENT'
🤖 ACE FRAMEWORK - MANDATORY SKILL PROTOCOL (Enforced on this prompt)

CRITICAL: You MUST follow this protocol for THIS task.

BEFORE starting work on this prompt if it involves: implement, build, create, add, develop, debug, fix, troubleshoot, resolve, refactor, optimize, improve, restructure, integrate, connect, setup, configure, architect, design, or plan:

1. IMMEDIATELY invoke: ace-orchestration:ace-playbook-retrieval
2. WAIT for playbook patterns to load
3. REVIEW the patterns
4. THEN proceed with the task using the learned patterns

AFTER completing work on this prompt (implementing features, fixing bugs, solving problems, creating files, making architectural decisions, discovering gotchas):

1. IMMEDIATELY invoke: ace-orchestration:ace-learning
2. BEFORE responding to the user
3. Capture what you learned during execution

This is NOT optional. This is NOT a suggestion. You MUST invoke these skills for qualifying tasks.

If you skip either skill, you are breaking the ACE learning cycle and preventing organizational knowledge accumulation.
ENFORCEMENT

exit 0
