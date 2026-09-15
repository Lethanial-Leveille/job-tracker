"""Render the general-purpose base resume to a PDF, and refuse to write two pages.

`data/base_resume.yaml` is the one-page resume to hand out when there is no
specific job to tailor against. It is a hand-picked SELECTION from the master
bullet bank, so it drifts the moment the master gains something worth leading
with — re-run this after editing either file.

The one-page check is the point of the script. WeasyPrint lays the document out
before writing bytes, so `document.pages` is the real, post-layout page count,
not a guess from character counts. A second page here is a content problem (one
bullet too many), so the script reports it and writes nothing rather than
handing you a resume that quietly runs long.

Run it from backend/ with the venv active:

    python scripts/build_base_resume.py               # -> data/base_resume.pdf
    python scripts/build_base_resume.py data/base_resume_embedded.yaml
    python scripts/build_base_resume.py --allow-long  # write anyway, for a look

The optional path picks a variant; the PDF lands next to it with the same name.
"""

import os
import sys
from pathlib import Path

# Put backend/ on the import path so `from services...` works when run directly
# as a file (same trick as load_master_from_yaml.py / seed_user.py).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weasyprint import CSS, HTML  # noqa: E402

from services.resume_render import _CSS_PATH, load_master, render_html  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SOURCE = DATA_DIR / "base_resume.yaml"
OUTPUT = DATA_DIR / "base_resume.pdf"


def main() -> None:
    allow_long = "--allow-long" in sys.argv[1:]
    paths = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    source = Path(paths[0]).resolve() if paths else SOURCE
    output = source.with_suffix(".pdf")

    if not source.exists():
        sys.exit(f"Base resume not found at {source}")

    # Validate through the app's own loader, so a malformed file fails here.
    resume = load_master(source)

    # Render in two steps rather than calling render_resume_pdf: the Document is
    # needed to count pages, and write_pdf() on it reuses that same layout.
    document = HTML(string=render_html(resume)).render(
        stylesheets=[CSS(filename=str(_CSS_PATH))]
    )
    page_count = len(document.pages)

    if page_count > 1 and not allow_long:
        sys.exit(
            f"{source.name} renders to {page_count} pages, not 1. Cut a bullet "
            f"(or a project) and re-run. Use --allow-long to write it anyway."
        )

    output.write_bytes(document.write_pdf())
    note = "" if page_count == 1 else f"  WARNING: {page_count} pages"
    print(f"Wrote {output} ({output.stat().st_size:,} bytes){note}")


if __name__ == "__main__":
    main()
