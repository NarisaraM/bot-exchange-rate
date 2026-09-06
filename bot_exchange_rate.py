"""
Fetch Bank of Thailand daily exchange rates and append them to a text file.

Data source: the JSON endpoint that
https://www.bot.or.th/th/statistics/exchange-rate.html itself calls.
It returns the most recently published day's rates (commercial-bank average,
Bangkok) for ~50 currencies, plus the weighted-average interbank USD/THB rate
(the "อัตราแลกเปลี่ยนถัวเฉลี่ยถ่วงน้ำหนักระหว่างธนาคาร" figure shown at the top
of the page), which is carried inside the JSON's "description" HTML.

No third-party packages required (uses only the standard library).

Output columns (tab-separated):
    date  currency  buying_sight  buying_transfer  selling  weighted_avg_interbank  fetched_at_utc

`weighted_avg_interbank` is a USD/THB-only figure, so it is filled in on the USD
row and left as "-" for every other currency.

Usage:
    python bot_exchange_rate.py                 # append USD row (incl. weighted avg)
    python bot_exchange_rate.py USD EUR JPY     # append several currencies
    python bot_exchange_rate.py --all           # append every currency
    python bot_exchange_rate.py --file rates.txt USD
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

# Windows consoles often default to a legacy code page; force UTF-8 so the
# Thai "last updated" string prints correctly.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

URL = (
    "https://www.bot.or.th/content/bot/th/statistics/exchange-rate/"
    "jcr:content/root/container/statisticstable2.results.level3cache.json"
)

DEFAULT_OUTFILE = "thb_exchange_rate.txt"
DEFAULT_CURRENCIES = ["USD"]
HEADER = ("# date\tcurrency\tbuying_sight\tbuying_transfer\tselling"
          "\tweighted_avg_interbank\tfetched_at_utc\n")


def fetch_payload():
    """Return the full decoded JSON payload from BOT."""
    req = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0 (exchange-rate-logger)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def parse_weighted_avg(description):
    """Pull the weighted-average interbank USD/THB rate out of the HTML blob.

    description looks like:
        <p>อัตราแลกเปลี่ยนถัวเฉลี่ยถ่วงน้ำหนักระหว่างธนาคาร&nbsp;
        <span ...>32.932</span>&nbsp;บาท ต่อ 1 ดอลลาร์ สรอ.</p>
    """
    if not description:
        return "-"
    text = re.sub(r"<[^>]+>", " ", description)          # drop HTML tags
    text = text.replace("&nbsp;", " ")
    match = re.search(r"\d+\.\d+", text)
    return match.group(0) if match else "-"


def load_existing_keys(path):
    """Set of 'date|CURRENCY' already present, so we never write a row twice."""
    keys = set()
    if not os.path.exists(path):
        return keys
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                keys.add(f"{parts[0]}|{parts[1]}")
    return keys


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("currencies", nargs="*", default=None,
                        help="Currency codes to record (default: USD)")
    parser.add_argument("--all", action="store_true",
                        help="Record every currency returned by BOT")
    parser.add_argument("--file", default=DEFAULT_OUTFILE,
                        help=f"Output text file (default: {DEFAULT_OUTFILE})")
    args = parser.parse_args()

    wanted = None
    if not args.all:
        wanted = {c.upper() for c in (args.currencies or DEFAULT_CURRENCIES)}

    try:
        payload = fetch_payload()
    except Exception as exc:  # noqa: BLE001 - report any network/parse failure plainly
        print(f"ERROR: could not fetch rates: {exc}", file=sys.stderr)
        return 1

    records = payload.get("responseContent", [])
    last_updated = payload.get("lastUpdated", "")
    weighted_avg = parse_weighted_avg(payload.get("description", ""))

    if not records:
        print("ERROR: endpoint returned no rate data", file=sys.stderr)
        return 1

    existing = load_existing_keys(args.file)
    new_header = not os.path.exists(args.file)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Date BOT assigns to this publication (ISO), taken from any record.
    pub_date = records[0].get("period", "")

    rows = []
    usd_emitted = False
    for rec in records:
        code = rec.get("currency_id", "").upper()
        if wanted is not None and code not in wanted:
            continue
        date = rec.get("period", "")  # ISO date, e.g. 2026-09-04
        key = f"{date}|{code}"
        if key in existing:
            continue
        rows.append("\t".join([
            date,
            code,
            rec.get("buying_sight", "-"),
            rec.get("buying_transfer", "-"),
            rec.get("selling", "-"),
            weighted_avg if code == "USD" else "-",
            fetched_at,
        ]))
        existing.add(key)
        if code == "USD":
            usd_emitted = True

    # If USD wasn't among the requested currencies, still record the
    # weighted-average interbank rate on its own row so it is never lost.
    if not usd_emitted and weighted_avg != "-" and f"{pub_date}|USD" not in existing:
        rows.append("\t".join([
            pub_date, "USD", "-", "-", "-", weighted_avg, fetched_at,
        ]))
        existing.add(f"{pub_date}|USD")

    if not rows:
        print(f"Nothing new to add (BOT last updated: {last_updated}).")
        return 0

    with open(args.file, "a", encoding="utf-8") as fh:
        if new_header:
            fh.write(HEADER)
        for row in rows:
            fh.write(row + "\n")

    print(f"BOT last updated: {last_updated}")
    print(f"Weighted-average interbank USD/THB: {weighted_avg}")
    print(f"Appended {len(rows)} row(s) to {os.path.abspath(args.file)}:")
    for row in rows:
        print("  " + row.replace("\t", "  "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
