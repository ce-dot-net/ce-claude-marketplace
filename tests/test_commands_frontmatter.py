"""WP-E (v8.0.0) — commands/*.md frontmatter.

DESIGN §6 WP-E: add `disable-model-invocation: true` to the user-only utilities
(everything except ace-search, ace-learn, ace-patterns, ace-status).
Critic T25 / docs-plugins §4: ~692 always-on tokens for 22 commands, ~500 removable.

Docs confirm commands honor it, so NO migration to skills/ is needed:
  plugins_components.md:271  "Command files take the same frontmatter as skills."
  skills.md:402/559          `disable-model-invocation: true` -> description not in context.
"""
from pathlib import Path

import pytest

COMMANDS = Path(__file__).resolve().parent.parent / "plugins" / "ace" / "commands"

MODEL_INVOCABLE = {"ace-search", "ace-learn", "ace-patterns", "ace-status"}
ALL_COMMANDS = sorted(p.stem for p in COMMANDS.glob("*.md"))
USER_ONLY = [c for c in ALL_COMMANDS if c not in MODEL_INVOCABLE]


def _frontmatter(name):
    text = (COMMANDS / (name + ".md")).read_text(encoding="utf-8")
    assert text.startswith("---\n"), name + ".md has no YAML frontmatter"
    block = text[4:].split("\n---", 1)[0]
    fm = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def test_command_set_is_the_known_22():
    """Guard: the user-only list below is computed from the real directory (22 commands)."""
    assert len(ALL_COMMANDS) == 22, ALL_COMMANDS
    assert MODEL_INVOCABLE <= set(ALL_COMMANDS)


@pytest.mark.parametrize("name", USER_ONLY)
def test_user_only_command_disables_model_invocation(name):
    """DESIGN §6 WP-E / critic T25: user-only utility must set disable-model-invocation: true."""
    assert _frontmatter(name).get("disable-model-invocation") == "true", (
        name + ".md must declare `disable-model-invocation: true` (user-only utility)"
    )


@pytest.mark.parametrize("name", sorted(MODEL_INVOCABLE))
def test_model_invocable_command_keeps_model_invocation(name):
    """DESIGN §6 WP-E: ace-search/learn/patterns/status stay model-invocable (ACE stays ON)."""
    assert _frontmatter(name).get("disable-model-invocation", "false") != "true"


@pytest.mark.parametrize("name", ALL_COMMANDS)
def test_every_command_keeps_a_description(name):
    """Guard: the frontmatter edit must not drop `description` (used by `/` menu)."""
    assert _frontmatter(name).get("description")


def test_commands_stay_in_commands_dir_no_skills_migration():
    """DESIGN §6 WP-E: docs confirm commands/*.md honor the key (plugins_components.md:271) -> keep commands/."""
    assert not (COMMANDS.parent / "skills").exists() or not any(
        (COMMANDS.parent / "skills").glob("ace-*/SKILL.md")
    ), "commands were migrated to skills/ although commands/ honors disable-model-invocation"


@pytest.mark.parametrize("name", ALL_COMMANDS)
def test_command_running_python_allows_python3(name):
    """WP-I: a command that runs an embedded `python3 - <<'PY'` block (ace-doctor A5,
    ace-cleanup --legacy) must allow `Bash(python3:*)` when it restricts allowed-tools."""
    text = (COMMANDS / (name + ".md")).read_text(encoding="utf-8")
    allowed = _frontmatter(name).get("allowed-tools")
    if allowed and "python3 - <<" in text:
        assert "Bash(python3:*)" in allowed, name + ".md runs python3 but allowed-tools lacks Bash(python3:*)"


@pytest.mark.parametrize("name", ["ace-doctor", "ace-cleanup"])
def test_round2_commands_embed_python_block(name):
    """WP-I (DESIGN §11 A5, §10 P-14): the checks are embedded stdlib python, run via heredoc."""
    text = (COMMANDS / (name + ".md")).read_text(encoding="utf-8")
    assert "python3 - " in text and "<<'PY'" in text, name + ".md must embed a `python3 - <<'PY'` block"
