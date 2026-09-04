"""Render a Resume into a styled PDF via a locked Jinja template + CSS.

This is the "renderer" from vision.md's resume-tailoring design, and the enforced
edge of the content vs format split. Claude tailoring only ever produces a Resume
(the content); it never touches templates/resume.html or templates/resume.css
(the format). Because the format is locked here, every generated PDF looks
identical no matter how many we produce, and the AI can't break the layout
because it can't see it.

Kept HTTP-ignorant like the other services: it takes a Resume and returns PDF
bytes, so a route, a test, or a one-off script can all call it the same way.
"""

import re
import unicodedata
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape
from weasyprint import CSS, HTML

from schemas.resume import Resume

# templates/ and this file's parent (services/) are siblings under backend/.
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_CSS_PATH = _TEMPLATES_DIR / "resume.css"

# autoescape on: bullet text is treated as data, so a stray "<" or "&" in resume
# content renders literally instead of being interpreted as markup.
_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

# Inline bold: a bullet may mark ONE fragment as **like this** and the renderer
# turns it into <strong>. This is the only formatting content is allowed to carry,
# and it exists because a skimming recruiter reads bold text first.
#
# ORDER MATTERS, and it is the whole security argument for this function: escape
# the text FIRST, then substitute the markers into the already-escaped string.
# Doing it the other way round (substitute, then hand markup to Jinja) would mean
# a "<" living in resume content could be interpreted as markup, so a stray angle
# bracket or a tailored bullet could inject tags into the PDF. Escaping first
# neutralises every "<" in the content, and the only "<" that survives is the
# <strong> this function writes itself.
_BOLD_MARKER = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def _bold(text: str) -> Markup:
    """Render **marked** spans as bold, treating everything else as literal text."""
    return Markup(_BOLD_MARKER.sub(r"<strong>\1</strong>", str(escape(text))))


_env.filters["bold"] = _bold


def render_resume_pdf(resume: Resume) -> bytes:
    """Render a validated Resume to PDF bytes.

    The CSS is passed explicitly (not linked from the HTML) so WeasyPrint needs
    no base_url to resolve it — the template stays pure structure.
    """
    html = _env.get_template("resume.html").render(r=resume)
    return HTML(string=html).write_pdf(stylesheets=[CSS(filename=str(_CSS_PATH))])


def _walk(box):
    """Every box in a laid-out tree, depth first."""
    yield box
    for child in getattr(box, "children", []):
        yield from _walk(child)


def _text_of(box) -> str:
    return "".join(b.text for b in _walk(box) if type(b).__name__ == "TextBox")


def count_lines_containing(resume: Resume, needle: str) -> int:
    """How many rendered LINES the block containing `needle` occupies.

    Same idea as count_pages, one level down. WeasyPrint's laid-out tree holds a
    LineBox per visual line, so this is the real wrapped line count — the only
    way to know, since whether a list of course names wraps depends on font
    metrics and the exact strings, not on how many items there are.

    Returns 0 when nothing matches, which includes the professional layout, where
    coursework is not rendered at all.
    """
    html = _env.get_template("resume.html").render(r=resume)
    document = HTML(string=html).render(stylesheets=[CSS(filename=str(_CSS_PATH))])
    for page in document.pages:
        for box in _walk(page._page_box):
            children = getattr(box, "children", [])
            # A block whose children are all LineBoxes is a run of wrapped text.
            if children and all(type(c).__name__ == "LineBox" for c in children):
                if needle in _text_of(box):
                    return len(children)
    return 0


def count_pages(resume: Resume) -> int:
    """How many pages this Resume actually renders to.

    The real, post-layout count: WeasyPrint lays the whole document out before
    writing any bytes, so `document.pages` is measured rather than estimated.
    Nothing else can answer this — line count depends on font metrics, wrapping,
    and margins, so no word or character budget predicts it (a 27-word bullet and
    a 24-word one routinely occupy the same three lines).

    Rendering the layout is the expensive half of producing a PDF, but it costs
    no API call and runs in a few hundred milliseconds, which is what makes a
    measure-then-trim loop practical.
    """
    html = _env.get_template("resume.html").render(r=resume)
    return len(HTML(string=html).render(stylesheets=[CSS(filename=str(_CSS_PATH))]).pages)


def load_master(path: str | Path) -> Resume:
    """Load and validate a master resume YAML file into a Resume."""
    data = yaml.safe_load(Path(path).read_text())
    return Resume.model_validate(data)


# --- Download filename -------------------------------------------------------
# "resume.pdf" is what every other candidate's attachment is called too, so it
# arrives in a recruiter's inbox as one more indistinguishable file and tells
# them nothing before they open it. The convention they expect is
# Lastname_Firstname_Resume.pdf, and when the resume is tailored, naming the
# company as well proves it was tailored at a glance.
_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9]+")


def _slug(text: str) -> str:
    """Fold to ASCII and keep only letters, digits, and single underscores.

    Two jobs, and the second one is why this is strict rather than clever:

    1. Filesystem safety. Slashes, colons, and spaces travel badly.
    2. HEADER SAFETY. This value is interpolated into a Content-Disposition
       header inside double quotes, so a company name containing a quote or a
       newline could otherwise close the quoted string early and append headers
       of its own. Company names reach us from parsed job postings, which is
       attacker-adjacent text, so the allowlist here is the actual defence — not
       the fact that a normal company name happens to look harmless.
    """
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return _FILENAME_SAFE.sub("_", folded).strip("_")


def resume_filename(resume: Resume, company: str | None = None) -> str:
    """Build "Leveille_Lethanial_Resume.pdf", plus "_Company" when tailored.

    The surname is taken as the LAST whitespace-separated token of the contact
    name and the given name as the first. That is a heuristic, and it is wrong
    for compound surnames ("van der Berg" yields "Berg") — worth knowing now that
    this is multi-user. It is still the right default because it is correct for
    the large majority of names and the alternative is asking every user to split
    their own name during onboarding for a filename. A user who needs it exact
    can rename the download.
    """
    parts = [p for p in (resume.contact.name or "").split() if p]
    if len(parts) >= 2:
        stem = f"{_slug(parts[-1])}_{_slug(parts[0])}_Resume"
    elif parts:
        stem = f"{_slug(parts[0])}_Resume"
    else:
        stem = "Resume"
    if company:
        suffix = _slug(company)
        if suffix:
            # Cap the company part so a pathological posting cannot produce a
            # filename long enough to be truncated or rejected downstream.
            stem = f"{stem}_{suffix[:40]}"
    return f"{stem.strip('_') or 'Resume'}.pdf"
