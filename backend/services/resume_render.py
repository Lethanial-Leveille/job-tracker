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

from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
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
