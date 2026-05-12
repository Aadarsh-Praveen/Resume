"""
LaTeX compilation utilities.

Wraps pdflatex, pdfinfo, and pdftoppm into clean Python functions with
full error capture so the tailoring pipeline can react to failures.
"""

import os
import re
import shutil
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

# Paths to system tools (can be overridden via env vars for testing)
PDFLATEX = os.getenv("PDFLATEX_BIN", "pdflatex")
PDFINFO = os.getenv("PDFINFO_BIN", "pdfinfo")
PDFTOPPM = os.getenv("PDFTOPPM_BIN", "pdftoppm")
PDFTOTEXT = os.getenv("PDFTOTEXT_BIN", "pdftotext")


def compile_tex(
    tex_content: str,
    output_dir: str,
    filename: str,
) -> Tuple[bool, str, str]:
    """
    Compile LaTeX source to PDF.

    Args:
        tex_content: Full .tex file content as a string.
        output_dir:  Directory where the final PDF should be placed.
        filename:    Base name for the output file (without extension).

    Returns:
        (success, pdf_path, error_log)
        - success:   True if compilation produced a valid PDF.
        - pdf_path:  Absolute path to the PDF (only meaningful when success=True).
        - error_log: Condensed pdflatex error output (empty string when success=True).
    """
    os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_file = os.path.join(tmpdir, f"{filename}.tex")
        pdf_src = os.path.join(tmpdir, f"{filename}.pdf")
        pdf_dst = os.path.join(output_dir, f"{filename}.pdf")

        with open(tex_file, "w", encoding="utf-8") as f:
            f.write(tex_content)

        # Run pdflatex twice so cross-references resolve correctly
        for _ in range(2):
            result = subprocess.run(
                [
                    PDFLATEX,
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    f"-output-directory={tmpdir}",
                    tex_file,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

        if result.returncode != 0 or not os.path.exists(pdf_src):
            error_log = _extract_errors(result.stdout + result.stderr)
            logger.warning("pdflatex failed for %s: %s", filename, error_log[:200])
            return False, "", error_log

        shutil.copy2(pdf_src, pdf_dst)
        logger.info("Compiled PDF: %s", pdf_dst)
        return True, os.path.abspath(pdf_dst), ""


def _extract_errors(log_output: str) -> str:
    """
    Pull the most relevant error lines from pdflatex output.
    Returns up to 20 lines that start with '!' or contain 'Error'.
    """
    lines = log_output.splitlines()
    error_lines = []
    capture_next = False
    for line in lines:
        if line.startswith("!") or "Error" in line or "Undefined control sequence" in line:
            error_lines.append(line)
            capture_next = True
        elif capture_next and line.strip():
            error_lines.append(line)
            capture_next = False
        if len(error_lines) >= 20:
            break
    return "\n".join(error_lines) if error_lines else log_output[-2000:]


def get_page_count(pdf_path: str) -> int:
    """
    Return the number of pages in a PDF.

    Tries pypdf first (pure Python, no system tools), then pdfinfo, then
    pdftotext form-feed counting. Returns -1 only if all three fail.
    """
    # Primary: pypdf — pure Python, no poppler/system tools required
    try:
        import pypdf
        with open(pdf_path, "rb") as _f:
            count = len(pypdf.PdfReader(_f).pages)
        logger.debug("pypdf page count: %d", count)
        return count
    except Exception as _e:
        logger.debug("pypdf page count failed: %s", _e)

    # Fallback 1: pdfinfo
    try:
        result = subprocess.run(
            [PDFINFO, pdf_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            if line.lower().startswith("pages:"):
                return int(line.split(":")[1].strip())
    except (subprocess.SubprocessError, FileNotFoundError, ValueError):
        pass

    # Fallback 2: pdftotext counts form-feed characters (one per page break)
    try:
        result = subprocess.run(
            [PDFTOTEXT, pdf_path, "-"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            pages = result.stdout.count("\f") + 1
            logger.debug("pdftotext page count fallback: %d pages", pages)
            return max(1, pages)
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    logger.warning("get_page_count: all methods unavailable for %s", pdf_path)
    return -1


def render_preview(pdf_path: str, dpi: int = 150):
    """
    Render the first page of a PDF as a PIL Image using PyMuPDF (fitz).

    Pure Python — no external binaries needed. If the PDF compiled successfully,
    this will always return a valid image.

    Returns a PIL.Image.Image on success, or None on failure.
    """
    try:
        import fitz  # PyMuPDF
        import PIL.Image
        doc = fitz.open(pdf_path)
        if not doc.page_count:
            logger.warning("render_preview: PDF has no pages: %s", pdf_path)
            return None
        pix = doc[0].get_pixmap(dpi=dpi)
        img = PIL.Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        doc.close()
        logger.info("render_preview: %dx%d px for %s", pix.width, pix.height, pdf_path)
        return img
    except Exception as e:
        logger.warning("render_preview failed: %s", e)
        return None


def measure_page_gap(img) -> float:
    """
    Measure the empty gap at the bottom of a rendered page image.

    Scans pixel rows from the bottom upward to find the last row that contains
    any content (non-white pixel). The gap is the fraction of page height below
    that row.

    Returns:
        Gap fraction 0.0–1.0.
        0.0  = content reaches the very bottom (or measurement failed).
        0.04 = 4% gap — within normal bottom-margin tolerance, treat as FULL.
        0.15 = 15% gap — obvious empty space, definitely SHORT.
    """
    try:
        gray = img.convert("L")
        w, h = gray.size
        pixels = list(gray.getdata())
        CONTENT_THRESHOLD = 230  # pixel value below this = ink/content (not white paper)

        last_content_row = 0
        for y in range(h - 1, -1, -1):
            row = pixels[y * w:(y + 1) * w]
            if any(p < CONTENT_THRESHOLD for p in row):
                last_content_row = y
                break

        gap = (h - last_content_row - 1) / h
        logger.debug("measure_page_gap: last content row %d/%d -> gap %.1f%%", last_content_row, h, gap * 100)
        return gap
    except Exception as e:
        logger.warning("measure_page_gap failed: %s -- assuming no gap", e)
        return 0.0  # assume OK on failure so we don't trigger unnecessary expansion


def adjust_margin(tex_content: str, margin_in: float) -> str:
    """
    Replace the \\geometry margin value in a .tex file.

    Clamps to [0.20, 0.25] inches.
    0.25in is the default and maximum (used for normal layout and SHORT recovery).
    0.20in is the minimum (used as last resort when trimming OVERFLOW).
    """
    margin_in = max(0.20, min(0.25, round(margin_in, 2)))
    return re.sub(
        r"(\\usepackage\[)[^\]]*?(]{geometry})",
        rf"\g<1>a4paper,margin={margin_in}in\g<2>",
        tex_content,
    )


def adjust_bottom_margin(tex_content: str, bottom_in: float) -> str:
    """
    Set only the bottom margin, keeping top/left/right at 0.25in.

    Used by the pixel safety net to absorb small page gaps without adding content.
    If the last content row sits at X% from the bottom of the page, setting
    bottom margin = X% * page_height eliminates the visible gap entirely.

    Clamps to [0.25, 0.75] inches (beyond 0.75in the gap is too large for margin
    absorption — content expansion is needed instead).
    """
    bottom_in = max(0.25, min(0.75, round(bottom_in, 3)))
    return re.sub(
        r"(\\usepackage\[)[^\]]*?(]{geometry})",
        rf"\g<1>a4paper,top=0.25in,left=0.25in,right=0.25in,bottom={bottom_in}in\g<2>",
        tex_content,
    )


def find_long_bullets(tex_content: str, max_words: int = 24) -> list[str]:
    """
    Find \\item bullets whose word count exceeds max_words.

    Bullets over 24 words risk wrapping to 3 lines on A4 at 11pt with 0.25in margins.
    Returns the raw LaTeX of each offending item (truncated to 120 chars) so they
    can be passed to a fix prompt.
    """
    items = re.findall(
        r"\\item\s+(.*?)(?=\\item|\\end\{(?:itemize|enumerate)\})",
        tex_content,
        re.DOTALL,
    )
    long = []
    for item in items:
        # Unwrap \cmd{text} -> text, then strip remaining commands/braces
        clean = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", item)
        clean = re.sub(r"\\[a-zA-Z]+", " ", clean)
        clean = re.sub(r"[{}\\%&$#_^~]", " ", clean)
        if len(clean.split()) > max_words:
            long.append(item.strip()[:120])
    return long


def sanitise_latex(tex_content: str) -> str:
    """
    LaTeX sanitiser applied before every pdflatex call.

    1. Strips ALL negative \\vspace{-...} — they cause company-line / bullet overlap.
    2. Removes product/domain labels from company lines (pipe-separated extras).
    3. Escapes bare % and & outside math/code environments.
    """
    result = tex_content

    # ── 1. Remove ALL negative \vspace ────────────────────────────────────────
    # Matches \vspace{-...} with any unit (pt, em, ex, mm, cm, in, bp, sp, dd, pc)
    result = re.sub(r"\\vspace\{-[^}]+\}", "", result)

    # ── 2. Strip pipe-separated product/domain labels from company lines ───────
    # Pattern: "CompanyName, City, ST $|$ \textit{...} \\"  →  "CompanyName \hfill City, ST \\"
    # Only match lines that end with \\ (company/role lines in resume)
    result = re.sub(
        r"(\\textbf\{[^}]+\}|[A-Za-z][\w\s,\.]+?)"   # company or role name
        r",\s*([^$\\]+?)"                               # ", City, ST"
        r"\s*\$\|\$\s*\\textit\{[^}]*\}"               # $|$ \textit{Product: ...}
        r"(\s*\\\\)",                                   # trailing \\
        lambda m: f"{m.group(1)} \\hfill {m.group(2).strip()}{m.group(3)}",
        result,
    )

    # ── 3. Escape bare % (not already escaped) ────────────────────────────────
    result = re.sub(r"(?<!\\)%", r"\\%", result)

    # ── 4. Escape bare & (not already escaped) ────────────────────────────────
    result = re.sub(r"(?<!\\)&", r"\\&", result)

    return result
