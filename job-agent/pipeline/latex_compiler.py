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


def sanitise_latex(tex_content: str) -> str:
    """
    Basic LaTeX sanitiser — escapes bare special characters that Claude
    occasionally produces outside of math/code environments.

    This is a defensive pass applied BEFORE sending to pdflatex.
    Only escapes % and & when they appear bare (not already preceded by backslash).
    """
    result = tex_content

    # Escape bare % (comments in LaTeX) — only when not already escaped
    result = re.sub(r"(?<!\\)%", r"\\%", result)

    # Escape bare & (table cell separators used in plain text) — only when not escaped
    # Skip if inside tabular/align environments — this is a best-effort pass
    result = re.sub(r"(?<!\\)&", r"\\&", result)

    return result
