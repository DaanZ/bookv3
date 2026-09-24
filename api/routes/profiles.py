"""The profile picker and each profile's settings: names, PINs, unlocking, devices, preferences, the Hardcover link."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api import positions, profiles
from api.deps import admin, self_or_owner

router = APIRouter()


class ProfileIn(BaseModel):
    name: str


class PinIn(BaseModel):
    """`pin` of null removes it; `current` proves you may change one that exists."""

    pin: str | None = None
    current: str | None = None


class UnlockIn(BaseModel):
    """A PIN, or a token from a device that has already answered one.

    `remember` asks for a token back, so the next ninety days on this device skip the
    digits entirely.
    """

    pin: str | None = None
    device: str | None = None
    remember: bool = False


class PrefsIn(BaseModel):
    """A patch, so the UI can send the one setting that moved. Every field is optional
    and anything unrecognised is dropped by `profiles.clean_prefs`."""

    theme: str | None = None
    palette: str | None = None
    maxHighlights: int | None = None


class HardcoverIn(BaseModel):
    """`token: null` unlinks the account. The token is never read back out."""

    token: str | None = None


@router.get("/api/profiles")
def get_profiles():
    """Everyone reading here, with enough of their progress to tell them apart."""
    rows = profiles.all_profiles()
    return {
        "profiles": [{**row, **positions.progress_of(row["id"])} for row in rows],
        "ownerId": profiles.owner()["id"],
    }


# Owner only. A new profile has no PIN, and a profile with no PIN is taken at its word, so
# an open "add a reader" on a public URL was a way for anybody to name themselves into the
# shelf. Adding a reader is the house deciding who reads here.
@router.post("/api/profiles", dependencies=[Depends(admin)])
def add_profile(body: ProfileIn):
    row, error = profiles.create(body.name)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return row


@router.patch("/api/profiles/{profile_id}", dependencies=[Depends(self_or_owner)])
def edit_profile(profile_id: str, body: ProfileIn):
    row, error = profiles.rename(profile_id, body.name)
    if error:
        raise HTTPException(status_code=404 if error == "No such profile." else 400, detail=error)
    return row


@router.put("/api/profiles/{profile_id}/pin", dependencies=[Depends(self_or_owner)])
def set_profile_pin(profile_id: str, body: PinIn):
    """Set, change or remove a profile's PIN.

    The digits are hashed in `profiles.set_pin` and never come back out — the response
    says `hasPin`, and that is all a browser is ever told about it.
    """
    row, error = profiles.set_pin(profile_id, body.pin, body.current)
    if error:
        raise HTTPException(status_code=404 if error == "No such profile." else 400, detail=error)
    return row


@router.post("/api/profiles/{profile_id}/unlock")
def unlock_profile(profile_id: str, body: UnlockIn, request: Request):
    """Check a PIN before the app switches into that profile.

    This is the lock on the picker. It is not access control: `X-Profile` remains a
    header a client asserts about itself, so this stops somebody picking up the tablet
    and reading as you — not somebody writing an HTTP request. Nothing on the reading
    endpoints consults it, and nothing should be built as though it did.
    """
    # A remembered device answers for itself. Checked first because it is the common
    # case on the tablet in your own house, and because a device that is still trusted
    # should never be rate limited for a PIN it was not asked for.
    if profiles.device_trusted(profile_id, body.device):
        return {"ok": True, "remembered": True}

    # Behind nginx `request.client.host` is the proxy unless uvicorn is told to trust
    # it — the unit passes --proxy-headers and --forwarded-allow-ips, without which every
    # guess in the world would share one bucket and lock the whole site out at try twelve.
    ok, error = profiles.check_pin(profile_id, body.pin, request.client.host if request.client else None)
    if ok:
        # Always minted, because the token is the session now: the reading endpoints
        # refuse a locked profile without one, so an unlock that handed back nothing
        # would let you in and lock the very next request. `remember` chooses how long
        # it lasts, not whether it exists.
        days = profiles.DEVICE_DAYS if body.remember else profiles.SESSION_HOURS / 24
        token, _ = profiles.remember_device(profile_id, days)
        return {
            "ok": True,
            "device": token,
            "days": profiles.DEVICE_DAYS if body.remember else 0,
            "remembered": bool(body.remember),
        }
    if error == "No such profile.":
        raise HTTPException(status_code=404, detail=error)
    # 429 for "you are guessing", 401 for "that is wrong" — the screen says different
    # things about them, and the retry-after only makes sense for one.
    raise HTTPException(status_code=429 if "wait" in error.lower() else 401, detail=error)


@router.post("/api/profiles/{profile_id}/forget-devices", dependencies=[Depends(self_or_owner)])
def forget_profile_devices(profile_id: str):
    """Stop trusting every remembered device for this profile.

    What you reach for when a tablet is lost or lent: the next open asks for the PIN
    again, everywhere.
    """
    row, error = profiles.forget_devices(profile_id)
    if error:
        raise HTTPException(status_code=404, detail=error)
    return row


@router.put("/api/profiles/{profile_id}/prefs", dependencies=[Depends(self_or_owner)])
def set_profile_prefs(profile_id: str, body: PrefsIn):
    """Register, palette, highlight cap — the settings the design calls the reader's
    rather than the app's, kept on the reader.

    By id rather than for whoever the header says, because that is what it is: a change
    to a named profile, which happens to almost always be the one holding the tablet.
    """
    row, error = profiles.set_prefs(profile_id, body.model_dump(exclude_none=True))
    if error:
        raise HTTPException(status_code=404, detail=error)
    return row


@router.put("/api/profiles/{profile_id}/hardcover", dependencies=[Depends(self_or_owner)])
def set_profile_hardcover(profile_id: str, body: HardcoverIn):
    """Link a reader's own Hardcover account, or unlink it.

    Per reader, because a finished book belongs to whoever read it. A profile with no
    token simply never reaches Hardcover — that is a setting, not a failure, and it is
    what makes the marking automatic for the one person who wants it and silent for
    everybody else who reads here.

    Like the PIN, the token goes in and does not come back: the response says
    `hasHardcover` and nothing more.
    """
    row, error = profiles.set_hardcover(profile_id, body.token)
    if error:
        raise HTTPException(status_code=404, detail=error)
    return row


@router.delete("/api/profiles/{profile_id}", dependencies=[Depends(self_or_owner)])
def drop_profile(profile_id: str):
    """Delete a profile and the reading it recorded. The books are untouched — they
    belong to the shelf, not to whoever was holding the tablet."""
    removed, error = profiles.remove(profile_id)
    if error:
        raise HTTPException(status_code=404 if error == "No such profile." else 400, detail=error)
    return {"deleted": removed}
