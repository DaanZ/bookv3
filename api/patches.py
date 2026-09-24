"""Category patches: the kind of book, readable before a word is read.

The handoff defines three patches exactly (spirituality / textiles / self-help) and says
to "extend by category, not by book". The repo's `meta.category` is free text produced by
the LLM, so it is normalised to a family here before it is looked up. Every colour below
comes from the Tide palettes; nothing is hand-picked.

Books written before `category` was added to the pipeline have no category at all — those
fall through to a deterministic patch derived from the family name, so a shelf row is
never patch-less.
"""

from hashlib import sha1

# The three from the handoff, verbatim.
FAMILIES: dict[str, dict] = {
    "spirituality": {"shape": "rings", "c1": "#0C617C", "c2": "#03B1AB", "c3": "#FFD167"},
    "textiles": {"shape": "checks", "c1": "#822E37", "c2": "#FDF6EA", "c3": "#BA5834"},
    "self-help": {"shape": "bands", "c1": "#67482F", "c2": "#E59312", "c3": "#F4B315"},
    # Extensions, same three geometries, colours taken from the palette tokens.
    "business": {"shape": "bands", "c1": "#0A2F33", "c2": "#12564F", "c3": "#3EA296"},
    "marketing": {"shape": "bands", "c1": "#822E37", "c2": "#BA5834", "c3": "#F68318"},
    "technology": {"shape": "checks", "c1": "#073A4B", "c2": "#03B1AB", "c3": "#0C617C"},
    "engineering": {"shape": "bands", "c1": "#423738", "c2": "#F4B315", "c3": "#108AB1"},
    "science": {"shape": "rings", "c1": "#313575", "c2": "#633090", "c3": "#FDC005"},
    "psychology": {"shape": "rings", "c1": "#321951", "c2": "#723466", "c3": "#E75480"},
    "history": {"shape": "checks", "c1": "#5C3210", "c2": "#FFE7C6", "c3": "#8A4A12"},
    "health": {"shape": "bands", "c1": "#12564F", "c2": "#06D7A0", "c3": "#FFD167"},
    "design": {"shape": "checks", "c1": "#6C2E7B", "c2": "#FFD8C7", "c3": "#FF8A5B"},
    "education": {"shape": "bands", "c1": "#0C617C", "c2": "#108AB1", "c3": "#FFD167"},
    "food": {"shape": "checks", "c1": "#8E5915", "c2": "#F4B315", "c3": "#B97515"},
    "fiction": {"shape": "rings", "c1": "#423738", "c2": "#8B7FD6", "c3": "#FFC857"},
}

# The colours a book's highlights burn in on the reading page, per family: smouldering,
# glowing, hot. `ink` is the text and `glow` the light behind it. They live here, beside
# the families, so the two cannot drift apart: this file is the one list of families, and
# the reader is sent the answer (`coals_for`) rather than keeping a copy keyed by name —
# a family renamed on one side used to fall through to the fire without a sound.
#
# Designed on the night ground, #1C1C1C, where every ink clears 4.5:1 as it stands
# (web/test/reading.test.mjs checks it). The `mood` is the brief each set was chosen to;
# it is not sent. `fire` is every family without its own, and a book with no category.
COALS: dict[str, dict] = {
    "psychology": {
        "mood": "the inner room · dusk · a lit window",
        "ink": ["#9A8FD1", "#D98BB5", "#FFB27A"],
        "glow": ["#4B3E8F", "#9C3F74", "#D9642A"],
    },
    "technology": {
        "mood": "screen light · signal · phosphor",
        "ink": ["#6FA8DC", "#4FD6E0", "#9CFF8A"],
        "glow": ["#2B5F94", "#138A96", "#3DAE2C"],
    },
    "engineering": {
        "mood": "steel · safety yellow · the arc of a weld",
        "ink": ["#A8B3BF", "#F2C94C", "#8FDBFF"],
        "glow": ["#56606B", "#B3860F", "#2A8FD1"],
    },
    "business": {
        "mood": "the ledger · slate · growth · gold",
        "ink": ["#8AA6C8", "#5FC9A8", "#F5CF5B"],
        "glow": ["#3D5A80", "#1E8A6B", "#C99A12"],
    },
    "self-help": {
        "mood": "morning · dawn · the sun coming up",
        "ink": ["#F0A3A3", "#FFB85C", "#FFE66B"],
        "glow": ["#B04A4A", "#D07A12", "#D9B400"],
    },
    "fire": {
        "mood": "the fire itself",
        "ink": ["#E65A64", "#F68318", "#FDC005"],
        "glow": ["#B22E37", "#C95F0C", "#E0A200"],
    },
}

# The first needle found in the list wins, so order is precedence: "self-help /
# productivity" lands on self-help because self-help is listed first. Engineering sits
# above technology for the same reason — "Technology & Engineering" is an engineering
# shelf, and the reader colours engineering's highlights differently.
KEYWORDS: list[tuple[str, str]] = [
    ("engineer", "engineering"),
    ("spiritual", "spirituality"), ("buddhis", "spirituality"), ("religio", "spirituality"),
    ("philosoph", "spirituality"), ("mindful", "spirituality"), ("medit", "spirituality"),
    ("textile", "textiles"), ("weav", "textiles"), ("craft", "textiles"),
    ("fashion", "textiles"), ("art", "textiles"),
    ("self-help", "self-help"), ("self help", "self-help"), ("personal development", "self-help"),
    ("productivity", "self-help"), ("habit", "self-help"), ("motivat", "self-help"),
    ("market", "marketing"), ("sales", "marketing"), ("advertis", "marketing"),
    ("brand", "marketing"), ("copywrit", "marketing"),
    ("business", "business"), ("econom", "business"), ("entrepreneur", "business"),
    ("manage", "business"), ("leader", "business"), ("finance", "business"),
    ("negoti", "business"), ("startup", "business"),
    ("comput", "technology"), ("program", "technology"), ("software", "technology"),
    ("technolog", "technology"), ("security", "technology"),
    ("data", "technology"), ("ux", "design"), ("interior", "design"),
    ("architect", "design"), ("design", "design"),
    ("psycholog", "psychology"), ("behavio", "psychology"), ("mind control", "psychology"),
    ("neuro", "psychology"), ("cognit", "psychology"),
    ("histor", "history"), ("archaeolog", "history"), ("biograph", "history"),
    ("politic", "history"), ("war", "history"),
    ("health", "health"), ("wellness", "health"), ("fitness", "health"),
    ("nutrit", "health"), ("medic", "health"),
    ("scien", "science"), ("physics", "science"), ("chemis", "science"),
    ("biolog", "science"), ("botan", "science"), ("math", "science"),
    ("educat", "education"), ("teach", "education"), ("learn", "education"),
    ("writing", "education"), ("research", "education"), ("academic", "education"),
    ("food", "food"), ("cuisine", "food"), ("cook", "food"), ("recipe", "food"),
    ("fiction", "fiction"), ("novel", "fiction"), ("story", "fiction"),
]

_SHAPES = ("rings", "checks", "bands")


def family_of(category: str | None) -> str:
    """Collapse the pipeline's free-text category onto a patch family."""
    if not category:
        return "uncategorised"
    text = category.strip().lower()
    if not text:
        return "uncategorised"
    for needle, fam in KEYWORDS:
        if needle in text:
            return fam
    # First segment of e.g. "Business Analysis, UX Design, Project Management".
    head = text.replace("/", ",").split(",")[0].strip()
    return head or "uncategorised"


def patch_for(category: str | None) -> dict:
    """A patch spec: shape plus three colours. Always returns something drawable."""
    fam = family_of(category)
    known = FAMILIES.get(fam)
    if known:
        return {"family": fam, **known}

    # Deterministic fallback so an unmapped family still reads as itself every time.
    digest = sha1(fam.encode("utf-8")).digest()
    shape = _SHAPES[digest[0] % len(_SHAPES)]
    ramp = [
        ["#0A2F33", "#1F7F76", "#F7A94A"],
        ["#313575", "#633090", "#FDC005"],
        ["#5C3210", "#C56A15", "#FFE7C6"],
        ["#073A4B", "#03B1AB", "#FFD167"],
        ["#423738", "#8E5915", "#F4B315"],
    ][digest[1] % 5]
    return {"family": fam, "shape": shape, "c1": ramp[0], "c2": ramp[1], "c3": ramp[2]}


def coals_for(family: str | None) -> dict:
    """The coal colours for a family, as the reader draws them: `ink` and `glow`."""
    coals = COALS.get(family or "", COALS["fire"])
    return {"ink": list(coals["ink"]), "glow": list(coals["glow"])}
