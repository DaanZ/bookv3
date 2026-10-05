"""What was read today, for other apps.

This is the one door that is not a reader's. Every other route under `/api` asks who is
holding the tablet and makes them prove it with a PIN; a calendar, a dashboard or a habit
tracker has no tablet and no PIN, so it gets a key of its own instead.

The key is `BOOKS_ACTIVITY_KEY`. **Off unless set**, for the reason `BOOKS_TRUSTED_PROFILE`
is: a deployment that never configured it must not grow a way in. It answers 404 then —
not 401 — so a stranger cannot tell the endpoint exists. It is read-only by construction:
there is no write route here to protect.

    curl -H "Authorization: Bearer $BOOKS_ACTIVITY_KEY" \
         "http://localhost:8001/api/activity/today?tz=Europe/Amsterdam"
"""

import hmac
import os
from datetime import date, datetime

from fastapi import APIRouter, Header, HTTPException, Query

from api import activity, profiles

router = APIRouter()

KEY_VAR = "BOOKS_ACTIVITY_KEY"


def _check_key(authorization: str | None) -> None:
    wanted = (os.environ.get(KEY_VAR) or "").strip()
    if not wanted:
        raise HTTPException(status_code=404, detail="Not found.")
    scheme, _, offered = (authorization or "").partition(" ")
    # compare_digest so the time taken does not say how many leading characters matched.
    if scheme.lower() != "bearer" or not hmac.compare_digest(offered.strip().encode(), wanted.encode()):
        raise HTTPException(
            status_code=401,
            detail="Send the activity key as 'Authorization: Bearer <key>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/api/activity/today")
def read_today(
    tz: str | None = Query(default=None, description="IANA timezone, e.g. Europe/Amsterdam. Defaults to this machine's clock."),
    day: date | None = Query(default=None, alias="date", description="YYYY-MM-DD instead of today. `finished` is exact for any day; `touched` only for today."),
    profile: str = Query(default="owner", description="A profile id, or `all` for every reader."),
    authorization: str | None = Header(default=None),
):
    """Books read on a day, one row per reader per book.

    A book is in the list when its last saved page fell on that day, and `finished` is
    true when it was also *finished* that day. `counts` separates the two, since "I
    opened four books" and "I finished one" are different things to show.
    """
    _check_key(authorization)

    try:
        zone = activity.zone_named(tz)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    everyone = profiles.all_profiles()
    if profile == "all":
        readers = everyone
    else:
        wanted = profiles.OWNER_ID if profile == "owner" else profile
        readers = [row for row in everyone if row["id"] == wanted]
        if not readers:
            raise HTTPException(status_code=404, detail="No such profile.")

    target = day or datetime.now(zone).date()
    books = activity.read_on(target, zone, readers)
    return {
        "date": target.isoformat(),
        "timezone": getattr(zone, "key", None) or str(zone),
        "books": books,
        "counts": {
            "touched": len(books),
            "finished": sum(1 for book in books if book["finished"]),
        },
    }
