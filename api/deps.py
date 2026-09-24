"""Who is asking, and what they may do: the two dependencies every route resolves through.

`reader` is a named profile that has proved it; `admin` is the owner; `self_or_owner` is
either of them acting on one profile. The whole permission model is these three functions,
kept in one place so it is never restated in a route.
"""

from fastapi import Depends, Header, HTTPException, Request

from api import profiles


def reader(
    request: Request,
    x_profile: str | None = Header(default=None),
    x_device: str | None = Header(default=None),
) -> dict:
    """Whose reading this request is.

    The profile travels in a header rather than the path, because it qualifies every
    endpoint here and none of them is *about* it.

    Two things have to be true, and they fail differently.

    **Somebody has to be asking.** There is no guest: a request with no profile, or one
    naming a profile that does not exist, is refused rather than handed the catalogue.
    The open catalogue was a rule about a tablet in a house, where the worst case was a
    visitor reading a summary. On a public URL it is an open door, and the door is now
    shut.

    **They have to prove it.** `X-Device` is what makes `X-Profile` more than a claim: a
    profile carrying a PIN must present the token its unlock minted. A profile with no
    PIN is taken at its word, which is the house model surviving where it still makes
    sense — but on a public deployment every profile should carry a PIN, and the two
    that exist do.

    401 for both, with different sentences, because the app does different things about
    them: one sends the reader to the picker, the other asks for the digits.

    **Unless this machine is trusted.** `BOOKS_TRUSTED_PROFILE` names a reader that
    requests from this computer are answered as, with no PIN — see `trusted_profile_for`
    for why that is opt-in and why a proxied deployment does not accidentally qualify.
    """
    address = request.client.host if request.client else None
    profile, verified = profiles.resolve(x_profile, x_device, address)
    if profile is None:
        raise HTTPException(
            status_code=401,
            detail="Pick a profile to read — the shelf belongs to somebody.",
        )
    if not verified:
        raise HTTPException(
            status_code=401,
            detail="That profile is locked. Enter its PIN to continue.",
        )
    return profile


def admin(profile: dict = Depends(reader)) -> dict:
    """The owner, and only them.

    What is *on* the shelf is the house's: adding a book, deleting one, re-filing one,
    and anything that reaches Hardcover. What somebody has *read of* it is the reader's,
    and that is the other dependency.

    The same caveat as the PIN applies and is worth repeating here, where it looks most
    like access control: `X-Profile` is asserted by the client, so this stops the app
    offering the library screen to a guest — not somebody writing an HTTP request. It is
    the house's rule about who adds books, enforced in one place instead of hidden in
    the UI, and it is not a permission system.
    """
    if not profile.get("owner"):
        raise HTTPException(
            status_code=403,
            detail="Only the owner adds, removes or re-files books.",
        )
    return profile


def self_or_owner(profile_id: str, profile: dict = Depends(reader)) -> dict:
    """The profile in the path, changed by its own reader or by the owner — nobody else.

    For everything that alters a profile rather than reads with one: its name, its PIN,
    its settings, its Hardcover link, its remembered devices, and deleting it. These were
    open once, on the house model's reasoning that everybody at the tablet is family. On a
    public URL that let anyone who could reach the server delete a reader and their
    history, point somebody's finishes at a Hardcover account of their own, or log every
    device out; and the picker offering Rename on every row was the UI saying the same.

    The owner may act on any profile because the owner already decides what is on the
    shelf, and handing a tablet over — renaming, removing a reader who has left — is
    theirs to do. 401 comes from `reader` for somebody who has not proved who they are;
    403 here is somebody who has, asking about a profile that is not theirs.
    """
    if profile.get("id") != profile_id and not profile.get("owner"):
        raise HTTPException(
            status_code=403,
            detail="That is somebody else's profile. Only they, or the owner, can change it.",
        )
    return profile

