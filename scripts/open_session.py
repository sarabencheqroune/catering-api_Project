"""
Restores a full Marjane session (cookies + localStorage: auth, cart, delivery)
from storage_state.json using Playwright, then opens the site in a real browser.
"""
from playwright.sync_api import sync_playwright

STORAGE_STATE_FILE = "storage_state.json"  # put this next to the script

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # visible window
    context = browser.new_context(storage_state=STORAGE_STATE_FILE)
    page = context.new_page()
    page.goto("https://www.marjane.ma")
    print("Session loaded. Browser will stay open — close it manually when done.")
    page.wait_for_timeout(1000 * 60 * 60)  # keep window open ~1hr; Ctrl+C to stop sooner