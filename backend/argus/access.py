"""Who may see what. Two roles, enforced here, not only in the console.

duty_officer  runs the floor: incidents, briefs, plain-language evidence, forecasts, patterns and coverage, and the
              decisions taken on the incident in front of them. Evidence reaches them without detector internals
              (track ids, raw strengths before profile weighting, rule measurements): need-to-know, and a smaller
              surface for anything that could single a person out.
supervisor    oversight and policy, on top of everything above: the whole hash-chained decision log and its export,
              detector internals per incident, what ARGUS has learned from dismissals (and resetting it), dismissed
              incidents (and reopening them), and the supervisor-only decisions (dismiss, police, site profile).

The role comes from the X-Argus-Role header (or the request body, for the older decision endpoints). With
ARGUS_SUPERVISOR_PIN set, a supervisor must also send it as X-Argus-Pin; unset (the demo), choosing the role is
enough. On a real site this is the site's single sign-on; the enforcement points stay the same.
"""
import hmac
import os
from typing import Literal

from fastapi import HTTPException, Request

Role = Literal["duty_officer", "supervisor"]
PUBLIC_ATTRS = {"live", "camera", "weapon", "reason", "view_lost_s", "story"}   # plain facts a duty officer may read


def pin_required() -> bool:
    return bool(os.environ.get("ARGUS_SUPERVISOR_PIN"))


def _pin_ok(pin: str | None) -> bool:
    want = os.environ.get("ARGUS_SUPERVISOR_PIN")
    return not want or (pin is not None and hmac.compare_digest(pin, want))


def role_of(request: Request, claimed: str | None = None) -> Role:
    """The caller's role. Claiming supervisor without the PIN (when one is set) is refused, not downgraded, so a
    wrong PIN never silently acts as a duty officer."""
    role = claimed or request.headers.get("x-argus-role") or "duty_officer"
    if role not in ("duty_officer", "supervisor"):
        raise HTTPException(400, f"unknown role {role!r}")
    if role == "supervisor" and not _pin_ok(request.headers.get("x-argus-pin")):
        raise HTTPException(401, "Supervisor PIN required")
    return role


def require_supervisor(request: Request, what: str) -> None:
    if role_of(request) != "supervisor":
        raise HTTPException(403, f"{what} is supervisor-only")


def for_duty_officer(event: dict) -> dict:
    """An event as a duty officer sees it: what happened, where, when and how strongly, without detector internals."""
    return {**event, "entity": None, "attrs": {k: v for k, v in (event.get("attrs") or {}).items() if k in PUBLIC_ATTRS}}
