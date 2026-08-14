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
    "science": {"shape": "rings", "c1": "#313575", "c2": "#633090", "c3": "#FDC005"},
    "psychology": {"shape": "rings", "c1": "#321951", "c2": "#723466", "c3": "#E75480"},
    "history": {"shape": "checks", "c1": "#5C3210", "c2": "#FFE7C6", "c3": "#8A4A12"},
    "health": {"shape": "bands", "c1": "#12564F", "c2": "#06D7A0", "c3": "#FFD167"},
    "design": {"shape": "checks", "c1": "#6C2E7B", "c2": "#FFD8C7", "c3": "#FF8A5B"},
    "education": {"shape": "bands", "c1": "#0C617C", "c2": "#108AB1", "c3": "#FFD167"},
    "food": {"shape": "checks", "c1": "#8E5915", "c2": "#F4B315", "c3": "#B97515"},
    "fiction": {"shape": "rings", "c1": "#423738", "c2": "#8B7FD6", "c3": "#FFC857"},
}

# Longest match wins, so "self-help / productivity" lands on self-help, not productivity.
KEYWORDS: list[tuple[str, str]] = [
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
    ("technolog", "technology"), ("engineer", "technology"), ("security", "technology"),
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
