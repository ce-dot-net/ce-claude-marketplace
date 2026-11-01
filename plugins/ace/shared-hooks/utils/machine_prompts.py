"""Machine-generated 'prompts' (DESIGN §8): one shared prefix list for UPS (WP-B) and Stop (WP-C)."""

MACHINE_PROMPT_PREFIXES = (
    '<task-notification', '<agent-message', '<cross-session-message', '[system notification',
    '<local-command', '<command-name>', '<bash-input>', '<bash-stdout>', '<bash-stderr>',
    '<system-reminder>',
)


def is_machine_prompt(text: str) -> bool:
    return (text or '').lower().lstrip().startswith(MACHINE_PROMPT_PREFIXES)
