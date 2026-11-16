"""Build docs/<name>.pdf from docs/<name>.md (needs: pip install markdown; Playwright + Chromium).

    python3 docs/build_pdf.py SAP_INTEGRATION "For the SAP Basis / ABAP / Integration team"
"""
import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

DOCS = Path(__file__).resolve().parent
CSS = """
@page { size: A4; }
body { font-family: 'Segoe UI', 'Noto Sans', Arial, sans-serif; color: #1f2420; font-size: 10.5pt; line-height: 1.5; }
.cover { background: #1b5e20; color: #fff; padding: 22px 26px; border-radius: 10px; margin-bottom: 18px; }
.cover .k { font-size: 9pt; letter-spacing: .12em; text-transform: uppercase; opacity: .85; }
.cover h1 { margin: 6px 0 4px; font-size: 21pt; } .cover p { margin: 0; opacity: .9; }
h2 { color: #1b5e20; border-bottom: 2px solid #d9e7da; padding-bottom: 4px; margin-top: 22px; font-size: 14.5pt; }
h3 { color: #2e4a30; margin-top: 16px; font-size: 12pt; }
h2, h3, p:has(+ table), p:has(+ ul), p:has(+ ol) { break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 9.5pt; break-inside: avoid; }
th { background: #1b5e20; color: #fff; text-align: left; padding: 6px 8px; }
td { border: 1px solid #dfe3dd; padding: 5px 8px; vertical-align: top; } tr:nth-child(even) td { background: #f6f8f5; }
code { font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 9pt; background: #eef2ec; padding: 1px 4px; border-radius: 3px; }
pre { background: #f3f5f2; border: 1px solid #dfe3dd; border-left: 4px solid #1b5e20; padding: 10px 12px; border-radius: 6px;
      white-space: pre-wrap; word-break: break-word; font-size: 8pt; line-height: 1.35; }
pre code { background: none; padding: 0; font-size: inherit; }
blockquote { margin: 12px 0; padding: 8px 14px; background: #fff7e0; border-left: 4px solid #eda100; border-radius: 4px; } blockquote p { margin: 0; }
hr { border: none; border-top: 1px solid #e3e6e1; margin: 18px 0; } li { margin: 3px 0; }
"""
JS = """
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('file://' + process.argv[2]);
  await p.pdf({ path: process.argv[3], format: 'A4', printBackground: true, displayHeaderFooter: true,
    headerTemplate: '<span></span>',
    footerTemplate: '<div style="font-size:8px;color:#888;width:100%;text-align:center;font-family:Arial">' + process.argv[4] +
      ' · page <span class="pageNumber"></span> / <span class="totalPages"></span></div>',
    margin: { top: '16mm', bottom: '18mm', left: '15mm', right: '15mm' } });
  await b.close();
})();
"""


def fix_lists(md: str) -> str:
    """Python-Markdown needs a blank line before a list and 4-space nesting."""
    out, fence = [], False
    for line in md.splitlines():
        if line.startswith("```"):
            fence = not fence
        if not fence:
            m = re.match(r"^( *)([-*]|\d+\.) ", line)
            if m:
                ind = len(m.group(1))
                if ind:
                    line = " " * (ind * 2) + line.lstrip()
                prev = out[-1] if out else ""
                if prev.strip() and not re.match(r"^ *([-*]|\d+\.) ", prev) and not prev.startswith("    "):
                    out.append("")
                elif not ind and prev.startswith("    "):
                    out.append("")
        out.append(line)
    return "\n".join(out)


def main(name: str, subtitle: str):
    src = fix_lists((DOCS / f"{name}.md").read_text(encoding="utf-8"))
    title = src.splitlines()[0].lstrip("# ").strip()
    body = markdown.markdown("\n".join(src.splitlines()[1:]), extensions=["tables", "fenced_code"])
    page = (f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
            f'<div class="cover"><div class="k">Customers Platform · Integration guide</div>'
            f'<h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>{body}</body></html>')
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "page.html").write_text(page, encoding="utf-8")
        (Path(d) / "pdf.js").write_text(JS)
        subprocess.run(["node", str(Path(d) / "pdf.js"), str(Path(d) / "page.html"), str(DOCS / f"{name}.pdf"),
                        f"Customers Platform · {title}"], check=True)
    print(DOCS / f"{name}.pdf")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "SAP_INTEGRATION",
         sys.argv[2] if len(sys.argv) > 2 else "For the SAP Basis / ABAP / Integration team.")
