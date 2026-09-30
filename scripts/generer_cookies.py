from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # navigateur visible, pour vous connecter à la main
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://www.marjane.ma/")
    input("Log in manually, then press Enter...")
    context.storage_state(path="storage_state.json")
    browser.close()
    print("Cookies sauvegardés dans storage_state.json")