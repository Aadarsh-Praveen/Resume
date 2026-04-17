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
    Return the number of pages in a PDF using pdfinfo.
    Returns -1 if pdfinfo is unavailable or the file cannot be read.
    """
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
        return -1
    except (subprocess.SubprocessError, FileNotFoundError, ValueError) as e:
        logger.warning("pdfinfo failed: %s", e)
        return -1


def get_fill_percentage(pdf_path: str) -> float:
    """
    Estimate how full a single-page PDF is (0.0–1.0).

    Uses pdftotext to count non-empty lines on the first page.
    A dense A4 resume at 10pt fills ~55 lines; we treat 50+ as "full".
    Returns 1.0 if pdftotext is unavailable (assume full → don't expand).
    """
    try:
        result = subprocess.run(
            [PDFTOTEXT, "-f", "1", "-l", "1", pdf_path, "-"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = [ln for ln in result.stdout.split("\n") if ln.strip()]
        # 50 non-empty lines ≈ full page; clamp to [0, 1]
        fill = min(len(lines) / 50.0, 1.0)
        logger.debug("Fill estimate: %d lines → %.0f%%", len(lines), fill * 100)
        return fill
    except Exception as e:
        logger.warning("get_fill_percentage failed: %s", e)
        return 1.0  # assume full — don't trigger unnecessary expansion


def render_preview(pdf_path: str, dpi: int = 150) -> str:
    """
    Render the first page of a PDF as a JPEG using pdftoppm.

    The image is written to the system temp directory (not alongside the PDF)
    so only .pdf files accumulate in the resumes/ folder.
    Callers are responsible for deleting the file after use.

    Args:
        pdf_path: Absolute path to the PDF.
        dpi:      Resolution for the preview image (default 150).

    Returns:
        Path to the generated JPEG file in /tmp, or empty string on failure.
    """
    stem = Path(pdf_path).stem
    output_prefix = os.path.join(tempfile.gettempdir(), f"{stem}_preview")
    try:
        result = subprocess.run(
            [
                PDFTOPPM,
                "-jpeg",
                "-r", str(dpi),
                "-l", "1",          # only first page
                "-singlefile",
                pdf_path,
                output_prefix,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        jpeg_path = f"{output_prefix}.jpg"
        if result.returncode == 0 and os.path.exists(jpeg_path):
            logger.info("Preview rendered: %s", jpeg_path)
            return jpeg_path
        logger.warning("pdftoppm failed: %s", result.stderr)
        return ""
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning("pdftoppm error: %s", e)
        return ""


def adjust_margin(tex_content: str, margin_in: float) -> str:
    """
    Replace the \\geometry margin value in a .tex file.

    Clamps to [0.20, 0.28] inches. Used when content overflows 1 page
    and we want to gain space by reducing margins before asking Claude to trim.
    """
    margin_in = max(0.20, min(0.28, round(margin_in, 2)))
    return re.sub(
        r"(\\usepackage\[)[^\]]*?(]{geometry})",
        rf"\g<1>a4paper,margin={margin_in}in\g<2>",
        tex_content,
    )



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
