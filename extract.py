"""Turn an uploaded file's bytes into Markdown-ish text. Standard library only.

.md / .markdown / .txt are decoded as UTF-8. .docx is read from its XML:
headings become "## " lines and list paragraphs become "- " bullets, so the
chunker and the to-do rules treat a Word document like a Markdown note. .pdf
works only when the `pdftotext` tool (poppler-utils) is installed.
"""

import io
import shutil
import subprocess
import zipfile
import xml.etree.ElementTree as ET

TEXT = {"md", "markdown", "txt"}
MAX_DOCX_XML = 20 * 1024 * 1024  # refuse zip bombs: document.xml larger than this
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def supported_extensions():
    exts = set(TEXT) | {"docx"}
    if shutil.which("pdftotext"):
        exts.add("pdf")
    return exts


class ExtractError(Exception):
    pass


def _docx(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_XML:
                raise ExtractError("this Word file is too large to read")
            root = ET.fromstring(z.read(info))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise ExtractError("this doesn't look like a Word (.docx) file") from None
    blocks = []
    for p in root.iter(W + "p"):
        text = "".join(t.text or "" for t in p.iter(W + "t")).strip()
        if not text:
            continue
        props = p.find(W + "pPr")
        style = ""
        if props is not None and props.find(W + "pStyle") is not None:
            style = props.find(W + "pStyle").get(W + "val", "").lower()
        if style.startswith("heading") or style == "title":
            blocks.append("## " + text)
        elif props is not None and props.find(W + "numPr") is not None or style.startswith("list"):
            blocks.append("- " + text)
        else:
            blocks.append(text)
    # Keep consecutive bullets together so they read as one list.
    out = []
    for block in blocks:
        joiner = "\n" if out and block.startswith("- ") and out[-1].split("\n")[-1].startswith("- ") else "\n\n"
        out.append(block if not out else joiner + block)
    return "".join(out)


def _pdf(data):
    tool = shutil.which("pdftotext")
    if not tool:
        raise ExtractError("PDF files aren't supported on this roost")
    try:
        done = subprocess.run([tool, "-layout", "-q", "-", "-"], input=data, capture_output=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise ExtractError("this PDF took too long to read") from None
    if done.returncode != 0:
        raise ExtractError("this PDF couldn't be read")
    return done.stdout.decode("utf-8", "replace")


def text_from(name, data):
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext in TEXT:
        return data.decode("utf-8", "replace")
    if ext == "docx":
        return _docx(data)
    if ext == "pdf":
        return _pdf(data)
    raise ExtractError(f"files of type .{ext or '?'} aren't supported")
