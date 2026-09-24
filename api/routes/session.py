"""Is the server up, and who does this machine answer as — the two questions asked before there is a reader."""

from fastapi import APIRouter, Header, Request

from api import jobs, library, profiles

router = APIRouter()


@router.get("/api/health")
def health():
    """Is the server up? Deliberately the one endpoint that asks nobody who they are.

    Everything else under `/api` now requires a named profile and a device token, which
    is right for reading and wrong for a readiness check: the Windows autostart scripts,
    the deploy script and anything watching the process need an answer *before* there is
    a reader, and a 401 is not the same as "down". It says nothing a stranger could not
    learn by loading the page.
    """
    # Counts, never titles. This endpoint answers strangers, and "how many books are
    # on the shelf" tells them nothing; "which book is being summarised right now"
    # would. The tray needs only the counts to choose a colour.
    from collections import Counter

    tally = Counter(job.get("status") for job in jobs.list_jobs(limit=200))
    return {
        "ok": True,
        "books": len(library.index()),
        "jobs": {
            "running": tally.get("running", 0) + tally.get("queued", 0),
            "failed": tally.get("failed", 0),
        },
    }


@router.get("/api/session")
def session(
    request: Request,
    x_profile: str | None = Header(default=None),
    x_device: str | None = Header(default=None),
):
    """Who the server would answer this caller as, without refusing anybody.

    The app cannot work this out for itself. It knows whether it holds a device token,
    but not whether this machine is trusted — and without asking, a trusted computer
    would still paint the PIN screen before discovering it did not need one. This is
    the one question `reader` cannot answer, because `reader`'s answer to "nobody" is
    a 401.

    `auto` is true when the answer came from the address rather than from anything the
    caller presented, which is what lets the picker say so rather than looking like a
    lock that failed to engage.
    """
    address = request.client.host if request.client else None
    profile, verified = profiles.resolve(x_profile, x_device, address)
    trusted = profiles.trusted_profile_for(address)
    return {
        "profile": profile if (profile and verified) else None,
        "auto": bool(trusted) and (profile or {}).get("id") == trusted,
    }
