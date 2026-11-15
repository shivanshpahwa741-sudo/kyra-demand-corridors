#!/usr/bin/env python3
"""
Daily scraper for Kyra admin. Uses Playwright persistent context so the login
session survives between runs. First run requires a visible login (run with
--bootstrap). After that, runs headless daily.
"""
import json, sys, time, argparse, os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / ".chrome-profile"
OUT_BOOKINGS = ROOT / "data" / "bookings.json"
OUT_BOOKINGS.parent.mkdir(exist_ok=True)

ADMIN_URL = "https://kyra-admin--kyrarides-8ec56.asia-southeast1.hosted.app/bookings"

SCRAPE_JS = r"""
async () => {
  // Set rows-per-page to 100
  const sel = document.querySelector('select');
  if (sel) { sel.value = '100'; sel.dispatchEvent(new Event('change', {bubbles: true})); }
  await new Promise(r => setTimeout(r, 1500));

  const rows = [];
  const scrape = () => {
    document.querySelectorAll('tbody tr').forEach(row => {
      const c = Array.from(row.querySelectorAll('td')).map(x => x.textContent.trim());
      const route = c[3] || '';
      const sep = route.indexOf('→');
      rows.push({
        booking: c[0], status: c[1], rider: c[2],
        from: sep >= 0 ? route.slice(0, sep).trim() : route,
        to: sep >= 0 ? route.slice(sep + 1).trim() : '',
        vehicle: c[4], fare: c[5], time: c[6],
      });
    });
  };
  const findNext = () => Array.from(document.querySelectorAll('button')).find(b => /Next/.test(b.textContent) && !b.disabled);
  const wait = (prev) => new Promise(resolve => {
    const start = Date.now();
    const iv = setInterval(() => {
      const f = document.querySelector('tbody tr td');
      if ((f && f.textContent.trim() !== prev) || Date.now() - start > 8000) { clearInterval(iv); resolve(); }
    }, 150);
  });
  scrape();
  for (let i = 0; i < 30; i++) {
    const prev = document.querySelector('tbody tr td')?.textContent.trim() || '';
    const btn = findNext(); if (!btn) break;
    btn.click(); await wait(prev); scrape();
  }
  return rows;
}
"""

def run(headless: bool):
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(ADMIN_URL, wait_until="networkidle", timeout=60000)
        # Detect login redirect
        if "/login" in page.url or "sign-in" in page.url.lower():
            if headless:
                print("ERROR: session expired, need to log in. Run: python3.12 scrape.py --bootstrap", file=sys.stderr)
                ctx.close()
                sys.exit(2)
            print("Please log in in the browser window, then press Enter here...")
            input()
            page.goto(ADMIN_URL, wait_until="networkidle", timeout=60000)

        page.wait_for_selector("tbody tr", timeout=30000)
        print(f"Scraping {ADMIN_URL}")
        rows = page.evaluate(SCRAPE_JS)
        print(f"Got {len(rows)} rows")

        OUT_BOOKINGS.write_text(json.dumps(rows, ensure_ascii=False))
        print(f"Wrote {OUT_BOOKINGS}")
        ctx.close()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", action="store_true", help="Run with visible browser to log in once")
    args = ap.parse_args()
    run(headless=not args.bootstrap)
