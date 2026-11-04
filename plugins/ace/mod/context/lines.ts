// One line per problem state, the adoption line and the `ace-cli init` warnings. GENERATED from ace_project_context.LINES / ADOPT_LINE
// (tests/test_project_context_service.py guards the parity): both chains show the same words.
export const LINES = {
 "unbound": "ACE ▼ Repo nicht verbunden: /ace:ace-configure",
 "not_logged_in": "ACE ▼ nicht angemeldet: /ace:ace-login",
 "expired": "ACE ▼ Anmeldung abgelaufen: /ace:ace-login",
 "project_not_found": "ACE ▼ Projekt nicht gefunden: /ace:ace-configure",
 "no_access": "ACE ▼ kein Zugriff auf das Projekt: /ace:ace-configure",
 "server_error": "ACE ▼ Server nicht erreichbar",
 "cli_missing": "ACE ▼ ace-cli fehlt: /ace:ace-install-cli",
 "config_refused": "ACE ▼ .ace/config.json enthält apiToken/serverUrl und wird ignoriert: /ace:ace-configure",
 "config_invalid": "ACE ▼ Bindungsdatei ist kein gültiges JSON: /ace:ace-doctor"
}
export const ADOPT_LINE = "ACE: Bindung als .ace/config.json gespeichert. Bitte committen, dann gilt sie in jedem Clone und auf jeder Maschine."
export const WARN_LINES = {
 "worktree_file_shadows_main": "ACE ▼ Dieser Worktree hat eine eigene .ace/config.json, die die Bindung des Haupt-Checkouts überschreibt",
 "worktree_topology_untrusted": "ACE ▼ Worktree-Struktur nicht verifizierbar (.git/commondir?): nichts in den Haupt-Checkout geschrieben"
}
