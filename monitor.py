"""Fetch each watched pricing page through Bright Data, check that it is
still the page you meant to watch, and diff its price lines against the
last snapshot. Prefer a site's Markdown version of a page when it has one.

Standard library only, so it runs in a fresh cloud VM without a setup script.
"""
import collections
import concurrent.futures
import datetime
import http.client
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).parent
SNAPSHOTS = ROOT / "snapshots"
REPORTS = ROOT / "reports"
API = "https://api.brightdata.com/request"
ZONE = os.environ.get("BRIGHTDATA_ZONE", "web_unlocker")
# A dollar amount such as $0.10, $2 or $1,250.00.
PRICE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")
# Markdown images and links, which make poor labels for a price.
LINKS = re.compile(r"!?\[[^\]]*\]\([^)]*\)")
# Sentence boundary, for prices that sit inside long prose lines.
SENTENCE = re.compile(r"(?<=[.!?])\s+")


def fetch(url, is_markdown=False):
    """Return (final_url, markdown). Raises when the fetch fails."""
    request = {"zone": ZONE, "url": url, "format": "raw"}
    if not is_markdown:
        # Rendered pages get converted. Markdown sources pass through as is.
        request["data_format"] = "markdown"
    body = json.dumps(request).encode()
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("BRIGHTDATA_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    # Without a key in the VM, a network secret on the cloud environment
    # adds the Authorization header after the request leaves the session.
    req = urllib.request.Request(API, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        # With format "raw", read unlock errors from x-brd-error as well
        # as from the status code.
        if resp.headers.get("x-brd-error"):
            raise urllib.error.URLError(resp.headers["x-brd-error"])
        # The target site's own status travels in x-brd-status-code.
        site_status = resp.headers.get("x-brd-status-code", "200")
        if not site_status.startswith("2"):
            raise urllib.error.URLError(f"site answered {site_status}")
        final_url = resp.headers.get("x-unblocker-redirected-to") or url
        return final_url, resp.read().decode("utf-8", "replace")


def price_lines(markdown):
    """Lines that carry a price, each prefixed with the 2 labels above it.

    Many pricing pages render each table cell on its own line, so a bare
    "$0.30" says nothing about which model changed. The labels fix that.
    Repeats are kept, so a change to one of 3 identical cells still shows.
    """
    lines, labels = [], []
    for raw in markdown.splitlines():
        line = re.sub(r"\s+", " ", raw).strip(" |*#-\\")
        if not line:
            continue
        if PRICE.search(line):
            # Pricing notes in long paragraphs: keep each priced sentence.
            parts = SENTENCE.split(line) if len(line) > 300 else [line]
            lines += [" > ".join(labels + [p]) for p in parts
                      if PRICE.search(p)]
        elif re.search("[A-Za-z]", LINKS.sub("", line)) and (
                len(line) <= 80 or raw.lstrip().startswith("|")):
            # Short text and table header rows label the prices below them.
            labels = (labels + [line])[-2:]
    return sorted(lines)


def check(page, final_url, markdown, lines):
    """Return the reasons this fetch is not the page we meant to watch."""
    problems = []
    if not final_url.startswith(page["expect_url_prefix"]):
        problems.append(f"redirected to {final_url}")
    for anchor in page["expect_text"]:
        if anchor.lower() not in markdown.lower():
            problems.append(f"missing anchor text '{anchor}'")
    if len(lines) < page["min_price_lines"]:
        problems.append(f"only {len(lines)} price lines, "
                        f"expected at least {page['min_price_lines']}")
    return problems


def run_one(page):
    for attempt in (1, 2):  # One retry covers a transient network error.
        try:
            final_url, markdown = fetch(page["url"], page.get("markdown"))
            break
        except (OSError, http.client.HTTPException) as e:
            if attempt == 2:
                return {"id": page["id"], "status": "fetch_failed",
                        "detail": str(e)}
            time.sleep(5)
    lines = price_lines(markdown)
    problems = check(page, final_url, markdown, lines)
    if problems:
        return {"id": page["id"], "status": "page_drifted",
                "detail": "; ".join(problems)}
    snap = SNAPSHOTS / f"{page['id']}.txt"
    old = snap.read_text().splitlines() if snap.exists() else None
    snap.write_text("\n".join(lines) + "\n")
    if old is None:
        return {"id": page["id"], "status": "baseline", "lines": len(lines)}
    new, prev = collections.Counter(lines), collections.Counter(old)
    added = sorted((new - prev).elements())
    removed = sorted((prev - new).elements())
    status = "changed" if added or removed else "unchanged"
    return {"id": page["id"], "status": status, "lines": len(lines),
            "added": added, "removed": removed}


def main():
    pages = json.loads((ROOT / "watchlist.json").read_text())
    SNAPSHOTS.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    # Remove the last report first, so a crash can't leave it looking new.
    (REPORTS / "latest.json").unlink(missing_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(run_one, pages))
    today = datetime.date.today().isoformat()
    (REPORTS / "latest.json").write_text(json.dumps(
        {"date": today, "results": results}, indent=1))
    for r in results:
        delta = (f"+{len(r['added'])} -{len(r['removed'])}"
                 if r["status"] == "changed" else "")
        print(f"{r['id']:<10} {r['status']:<13} {r.get('detail', '')}{delta}")
    # A non-zero exit makes a broken watchlist visible in the run transcript.
    sys.exit(1 if any(r["status"] in ("fetch_failed", "page_drifted")
                      for r in results) else 0)


if __name__ == "__main__":
    main()
