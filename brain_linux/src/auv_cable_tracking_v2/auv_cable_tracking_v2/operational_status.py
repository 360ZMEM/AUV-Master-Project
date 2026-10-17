"""Operator-facing inspection status derived from the effective bridge decision."""

from __future__ import annotations


def build_operational_status(*, mode: str, source: str, mpc_valid: bool,
                             guard_state: str, guard_reason: str,
                             budget_problem: str | None, passive: bool,
                             localization_status: str, localization_fresh: bool) -> dict:
    """Keep localization evidence separate from permission to send autonomous commands.

    This describes bridge authority, not vehicle motion or station keeping.
    """
    if passive:
        reason = 'bridge_passive_mode'
    elif guard_state != 'ACTIVE':
        reason = guard_reason if guard_reason != 'NONE' else 'guard_not_active'
    elif budget_problem:
        reason = budget_problem
    elif mode != 'AUTONOMOUS':
        reason = 'remote_mode'
    elif source != 'JETSON_MPC' or not mpc_valid:
        reason = 'mpc_command_unavailable'
    else:
        reason = ''
    return {
        'autonomous_execution_authorized': not bool(reason),
        'authority_reason': reason,
        'arbiter_mode': mode,
        'arbiter_source': source,
        'guard_state': guard_state,
        'guard_reason': guard_reason,
        'localization_status': localization_status if localization_fresh else 'UNKNOWN',
        'localization_status_fresh': localization_fresh,
    }
