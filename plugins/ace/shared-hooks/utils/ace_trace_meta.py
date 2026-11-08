"""8.1.4: what every automatic trace says about the client, inside `result` (the server keeps task, trajectory, result,
playbook_used, timestamp, git of trace_json; a top-level field would be dropped).

OUTCOME_RULES is a fixed, documented list (CHANGELOG [8.1.4], DESIGN "Trace delivery"); mod/lib/trace.ts carries the
same list (parity test). A future rule change bumps the number and adds a value here and there.
"""
RULE_END = "end-outcome-1"            # 8.1.3+: result.success = the end outcome of the task (Stop, SubagentStop, mod turn.complete)
RULE_PERMISSION = "permission-gate-1"  # 7.1.14+: a PermissionDenied trace (success false, one failed step)
OUTCOME_RULES = (RULE_END, RULE_PERMISSION)


def stamp(trace, rule):
    """result.plugin_version (manifest x.y.z, the version in X-ACE-Client) + result.outcome_rule; returns trace."""
    from ace_env import plugin_version
    if rule not in OUTCOME_RULES:
        raise ValueError("unknown outcome rule: %r" % rule)
    res = trace.get("result")
    if not isinstance(res, dict):
        res = trace["result"] = {}
    res["plugin_version"] = plugin_version()
    res["outcome_rule"] = rule
    return trace
