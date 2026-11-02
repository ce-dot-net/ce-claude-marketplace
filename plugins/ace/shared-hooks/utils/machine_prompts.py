"""Machine-generated 'prompts' (DESIGN §8): one shared prefix list for UPS (WP-B) and Stop (WP-C)."""
import os

MACHINE_PROMPT_PREFIXES = (
    '<task-notification', '<agent-message', '<cross-session-message', '[system notification',
    '<local-command', '<command-name>', '<bash-input>', '<bash-stdout>', '<bash-stderr>',
    '<system-reminder>',
)


def _prefixes():
    # ACE_MACHINE_PROMPT_PREFIXES: comma list for local daemon prompts (e.g. "zustellung,coachd:")
    extra = tuple(x.strip().lower() for x in os.environ.get('ACE_MACHINE_PROMPT_PREFIXES', '').split(',') if x.strip())
    return MACHINE_PROMPT_PREFIXES + extra


def is_machine_prompt(text: str) -> bool:
    return (text or '').lower().lstrip().startswith(_prefixes())
