"""
.docx -> .pdf, and how many pages it came to.

Microsoft Word does the conversion when it is installed (Windows): the PDF is
then exactly what Word shows for the .docx, and Word also reports the page
count and how far down the last page the text reaches — what the length
fitting in cv_tailor needs. Word is driven through COM from one PowerShell
process kept open for the whole tailoring run: starting Word took 45 s on the
owner's laptop (2026-10-06), a conversion in an open Word about 2 s.

Without Word, LibreOffice (`soffice --headless --convert-to pdf`) converts,
and the page count is read from the PDF. Without either, there is no PDF and
the caller says so.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional

WORD_TIMEOUT_SECONDS = 180

# Reads one JSON request per line: {"docx": ..., "pdf": ...}; answers one
# JSON line: {"pages": N, "last_page_bottom_pt": y} or {"error": ...}.
# 17 = wdExportFormatPDF, 2 = wdStatisticPages, 6 =
# wdVerticalPositionRelativeToPage, 0 = wdDoNotSaveChanges.
WORD_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$word = $null
try {
  $word = New-Object -ComObject Word.Application
  $word.Visible = $false
  $word.DisplayAlerts = 0
  [Console]::Out.WriteLine('{"ready": true}')
  [Console]::Out.Flush()
  while ($true) {
    $line = [Console]::In.ReadLine()
    if ($line -eq $null -or $line -eq '') { break }
    try {
      $request = $line | ConvertFrom-Json
      $doc = $word.Documents.Open($request.docx, $false, $true, $false)
      $doc.Repaginate()
      $pages = $doc.ComputeStatistics(2)
      $end = $doc.Content
      $end.Collapse(0)
      $bottom = $end.Information(6)
      if ($request.pdf) { $doc.ExportAsFixedFormat($request.pdf, 17) }
      $doc.Close(0)
      $answer = @{ pages = $pages; last_page_bottom_pt = $bottom } | ConvertTo-Json -Compress
    } catch {
      $answer = @{ error = $_.Exception.Message } | ConvertTo-Json -Compress
    }
    [Console]::Out.WriteLine($answer)
    [Console]::Out.Flush()
  }
} catch {
  [Console]::Out.WriteLine((@{ error = $_.Exception.Message } | ConvertTo-Json -Compress))
} finally {
  if ($word -ne $null) {
    $word.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($word)
  }
}
"""


class ConversionError(RuntimeError):
    pass


class WordSession:
    """One Word for several conversions. Use as a context manager."""

    def __init__(self, timeout: float = WORD_TIMEOUT_SECONDS):
        self.timeout = timeout
        self.process: Optional[subprocess.Popen] = None
        self.script: Optional[Path] = None

    def __enter__(self) -> "WordSession":
        # The script goes into a file: with "-Command -" PowerShell would read
        # the requests on stdin as more script.
        handle, script = tempfile.mkstemp(suffix=".ps1", prefix="workide_word_")
        with os.fdopen(handle, "w", encoding="utf-8-sig") as file:
            file.write(WORD_SCRIPT)
        self.script = Path(script)
        self.process = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(self.script)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        answer = self._read()
        if not answer.get("ready"):
            self.close()
            raise ConversionError(f"Word did not start: {answer.get('error', answer)}")
        return self

    def convert(self, docx: Path, pdf: Optional[Path]) -> dict:
        """Opens `docx` in Word; writes `pdf` when given. Returns
        {"pages": N, "last_page_bottom_pt": y}."""
        request = {"docx": str(Path(docx).resolve()), "pdf": str(Path(pdf).resolve()) if pdf else ""}
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        answer = self._read()
        if "error" in answer:
            raise ConversionError(f"Word: {answer['error']}")
        return {"pages": int(answer["pages"]), "last_page_bottom_pt": float(answer["last_page_bottom_pt"])}

    def _read(self) -> dict:
        result = {}

        def read_line():
            while True:
                line = self.process.stdout.readline()
                if not line:
                    result["error"] = "Word's process ended: " + (self.process.stderr.read() or "").strip()[:500]
                    return
                line = line.strip()
                if line.startswith("{"):
                    try:
                        result.update(json.loads(line))
                        return
                    except json.JSONDecodeError:
                        continue

        reader = threading.Thread(target=read_line, daemon=True)
        reader.start()
        reader.join(self.timeout)
        if reader.is_alive():
            self.close(kill=True)
            raise ConversionError(f"Word did not answer in {self.timeout:.0f} s")
        return result

    def close(self, kill: bool = False) -> None:
        if not self.process:
            return
        try:
            if kill:
                subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                               capture_output=True, check=False)
            else:
                self.process.stdin.write("\n")
                self.process.stdin.flush()
                self.process.stdin.close()
                self.process.wait(timeout=60)
        except Exception:  # noqa: BLE001 — closing must not hide the real result
            subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                           capture_output=True, check=False)
        self.process = None
        if self.script:
            self.script.unlink(missing_ok=True)
            self.script = None

    def __exit__(self, *exc) -> None:
        self.close()


def word_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID"):
            return True
    except OSError:
        return False


def soffice_path() -> Optional[str]:
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
        candidate = Path(base) / "LibreOffice" / "program" / "soffice.exe"
        if base and candidate.exists():
            return str(candidate)
    return None


def libreoffice_convert(docx: Path, pdf: Path) -> dict:
    soffice = soffice_path()
    if not soffice:
        raise ConversionError("neither Microsoft Word nor LibreOffice is installed")
    out_dir = Path(pdf).parent
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx)],
                   capture_output=True, check=True, timeout=WORD_TIMEOUT_SECONDS)
    produced = out_dir / (Path(docx).stem + ".pdf")
    if produced != Path(pdf):
        produced.replace(pdf)
    return {"pages": pdf_page_count(Path(pdf)), "last_page_bottom_pt": None}


def pdf_page_count(path: Path) -> int:
    """The /Count of the page tree's root: the largest /Count of a /Pages
    object. Good enough for the PDFs Word and LibreOffice write, which keep
    the page tree outside compressed object streams."""
    data = Path(path).read_bytes()
    counts = [int(m.group(1)) for m in re.finditer(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", data)]
    counts += [int(m.group(1)) for m in re.finditer(rb"/Count\s+(\d+)[^>]*?/Type\s*/Pages\b", data)]
    return max(counts) if counts else 0
