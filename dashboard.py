"""Render reports/latest.json as a self-contained HTML dashboard page."""
import html
import json
import pathlib

ROOT = pathlib.Path(__file__).parent
STATUS = {"changed": "warn", "page_drifted": "bad", "fetch_failed": "bad",
          "unchanged": "ok", "baseline": "ok"}

STYLE = """
/* Layout: one column, summary chips, then one row per watched page. */
:root { --bg: #f6f7f9; --panel: #ffffff; --fg: #1b2330; --muted: #5d6878;
  --line: #dde2ea; --ok: #1f7a4d; --warn: #9a5b00; --bad: #b42318;
  --sans: "Public Sans", system-ui, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, monospace; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #11151c; --panel: #171d26; --fg: #e6eaf0; --muted: #9aa5b5;
  --line: #2a3340; --ok: #4cc38a; --warn: #f0b354; --bad: #ff8a7a;
  color-scheme: dark } }
:root[data-theme="dark"] { --bg: #11151c; --panel: #171d26; --fg: #e6eaf0;
  --muted: #9aa5b5; --line: #2a3340; --ok: #4cc38a; --warn: #f0b354;
  --bad: #ff8a7a; color-scheme: dark }
body { background: var(--bg); color: var(--fg); font: 15px/1.5 var(--sans);
  padding-inline: 16px; padding-block: 24px 40px }
main { max-width: 860px; margin: 0 auto; display: grid; gap: 16px }
h1 { font-size: 22px; margin: 0; text-wrap: balance }
.meta { color: var(--muted); font-size: 13px }
.chips { display: flex; flex-wrap: wrap; gap: 8px }
.chip, .pill { border: 1px solid var(--line); border-radius: 999px;
  padding: 2px 10px; font-size: 13px; font-variant-numeric: tabular-nums }
.ok { color: var(--ok) } .warn { color: var(--warn) }
.bad { color: var(--bad) }
.page { background: var(--panel); border: 1px solid var(--line);
  border-radius: 8px; padding: 12px 14px; display: grid; gap: 6px;
  min-width: 0 }
.head { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline }
.head b { font-family: var(--mono); font-size: 14px }
.detail { color: var(--muted); font-size: 13px; overflow-wrap: anywhere }
pre { font: 12px/1.45 var(--mono); margin: 0; overflow-x: auto;
  white-space: pre; padding: 8px; background: var(--bg); border-radius: 6px }
"""


def render(report):
    results = report["results"]
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    chips = "".join(
        f'<span class="chip {STATUS.get(k, "")}">{n} {html.escape(k)}</span>'
        for k, n in sorted(counts.items()))
    order = {"bad": 0, "warn": 1, "ok": 2}
    rows = []
    for r in sorted(results,
                    key=lambda r: order[STATUS.get(r["status"], "bad")]):
        cls = STATUS.get(r["status"], "bad")
        detail = html.escape(r.get("detail", ""))
        diff = "".join(f"- {html.escape(x)}\n"
                       for x in r.get("removed", []))
        diff += "".join(f"+ {html.escape(x)}\n" for x in r.get("added", []))
        rows.append(
            '<section class="page"><div class="head">'
            f'<b>{html.escape(r["id"])}</b>'
            f'<span class="pill {cls}">{html.escape(r["status"])}</span>'
            + (f'<span class="meta">{r["lines"]} price lines</span>'
               if "lines" in r else "") + "</div>"
            + (f'<div class="detail">{detail}</div>' if detail else "")
            + (f"<pre>{diff}</pre>" if diff else "") + "</section>")
    return ("<title>LLM Price Watch</title>\n"
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
            'family=JetBrains+Mono&family=Public+Sans:wght@400;600'
            '&display=swap">\n'
            f"<style>{STYLE}</style>\n<main><h1>LLM Price Watch</h1>"
            f'<div class="meta">Run date {html.escape(report["date"])}, '
            f"{len(results)} pages watched</div>"
            f'<div class="chips">{chips}</div>{"".join(rows)}</main>\n')


if __name__ == "__main__":
    latest = ROOT / "reports" / "latest.json"
    if latest.exists():
        report = json.loads(latest.read_text())
    elif not any((ROOT / "snapshots").glob("*.txt")):
        # A fresh fork has no runs yet, so the first dashboard is a placeholder.
        report = {"date": "pending first run", "results": []}
    else:
        raise SystemExit("reports/latest.json is missing. Run monitor.py first.")
    latest.parent.mkdir(exist_ok=True)
    (ROOT / "reports" / "dashboard.html").write_text(render(report))
