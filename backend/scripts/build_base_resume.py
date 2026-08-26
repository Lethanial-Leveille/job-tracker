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
    python scripts/build_base_resume.py --allow-long  # write anyway, for a look
"""

import os
import sys
from pathlib import Path

# Put backend/ on the import path so `from services...` works when run directly
# as a file (same trick as load_master_from_yaml.py / seed_user.py).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weasyprint import CSS, HTML  # noqa: E402

from services.resume_render import _CSS_PATH, _env, load_master  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SOURCE = DATA_DIR / "base_resume.yaml"
OUTPUT = DATA_DIR / "base_resume.pdf"


def main() -> None:
    allow_long = "--allow-long" in sys.argv[1:]

    if not SOURCE.exists():
        sys.exit(f"Base resume not found at {SOURCE}")

    # Validate through the app's own loader, so a malformed file fails here.
    resume = load_master(SOURCE)

    # Render in two steps rather than calling render_resume_pdf: the Document is
    # needed to count pages, and write_pdf() on it reuses that same layout.
    html = _env.get_template("resume.html").render(r=resume)
    document = HTML(string=html).render(stylesheets=[CSS(filename=str(_CSS_PATH))])
    page_count = len(document.pages)

    if page_count > 1 and not allow_long:
        sys.exit(
            f"{SOURCE.name} renders to {page_count} pages, not 1. Cut a bullet "
            f"(or a project) and re-run. Use --allow-long to write it anyway."
        )

    OUTPUT.write_bytes(document.write_pdf())
    note = "" if page_count == 1 else f"  WARNING: {page_count} pages"
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes){note}")


if __name__ == "__main__":
    main()
