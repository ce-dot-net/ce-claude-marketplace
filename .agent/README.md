# Native ACE Pack for Antigravity

This pack allows you to use ACE (Agentic Context Engine) within Antigravity without modifying your project's code.

## Setup

1. **Install CLI**: Run `/ace_start` to automatically check for and install the `ce-ace` CLI.
2. **Configure**: Run `/ace_configure` to set your Organization and Project IDs.

## Usage

### Start a Task
Run `/ace_start` at the beginning of a task to search for relevant patterns.
```bash
/ace_start
```
*Follow the instructions to replace `YOUR_QUERY` with your task description.*

### Finish a Task
Run `/ace_finish` at the end of a task to capture learning.
```bash
/ace_finish
```
*Follow the instructions to provide task details and success status.*

### Advanced Features
- **/ace_bootstrap**: Initialize your playbook from the codebase.
- **/ace_doctor**: Check system health and diagnostics.
- **/ace_status**: View playbook statistics.
- **/ace_patterns**: List all learned patterns.

## Directory Structure
- `.agent/ace/`: Contains the adapter script and installer.
- `.agent/workflows/`: Contains the workflow definitions.
