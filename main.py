from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from playwright_stealth import Stealth
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
import os, uuid, shutil

app = FastAPI()

API_KEY = os.environ["API_KEY"]

# ---------------------------------------------------------------------
# Cookie storage
# ---------------------------------------------------------------------
# Render's "Secret Files" are mounted read-only at /etc/secrets/<name>, so
# they can only ever be the *initial seed* of storage_state.json -- we can't
# write refreshed cookies back to that path (Playwright's
# context.storage_state(path=...) call would fail with a permission error).
#
# On boot, copy the secret's contents into a writable directory (COOKIES_DIR)
# if nothing is there yet, and read/write exclusively from that writable copy
# afterwards. On Render's free plan there's no Persistent Disk available, so
# this writable copy is ephemeral -- it resets every time the free instance
# spins down and back up (which happens after ~15min idle). In practice
# that's fine here: the long-lived JWT in the "auth" localStorage entry
# (roughly a year's validity) is what actually keeps the account logged in,
# and short-lived Cloudflare cookies (__cf_bm etc.) get re-issued naturally
# the moment the browser loads marjane.ma each run. If the login ever does
# go stale, rerun generer_cookies.py locally and re-upload the Render
# Secret File -- there's no automatic persistence to fall back on here.
SECRET_SEED_PATH = "/etc/secrets/storage_state.json"
COOKIES_DIR = os.environ.get("COOKIES_DIR", "/var/data")
COOKIES_PATH = os.path.join(COOKIES_DIR, "storage_state.json")


def ensure_cookies_seeded():
    os.makedirs(COOKIES_DIR, exist_ok=True)
    if not os.path.exists(COOKIES_PATH) and os.path.exists(SECRET_SEED_PATH):
        shutil.copyfile(SECRET_SEED_PATH, COOKIES_PATH)


ensure_cookies_seeded()

# ---------------------------------------------------------------------
# Morocco-geotargeted proxy
# ---------------------------------------------------------------------
# Marjane blocks requests coming from outside Morocco. Render's own
# datacenters aren't in Morocco, so every browser launch needs to go
# through a Morocco-geotargeted proxy (residential proxy provider).
# Leave PROXY_SERVER unset to run without a proxy (e.g. local testing
# from a Moroccan connection).
PROXY_SERVER = os.environ.get("PROXY_SERVER")      # e.g. "http://gate.proxyprovider.com:8000"
PROXY_USERNAME = os.environ.get("PROXY_USERNAME")
PROXY_PASSWORD = os.environ.get("PROXY_PASSWORD")


def get_proxy_config():
    if not PROXY_SERVER:
        return None
    cfg = {"server": PROXY_SERVER}
    if PROXY_USERNAME:
        cfg["username"] = PROXY_USERNAME
    if PROXY_PASSWORD:
        cfg["password"] = PROXY_PASSWORD
    return cfg


def check_auth(x_api_key: str):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/debug")
def debug():
    return {
        "cookies_path": COOKIES_PATH,
        "file_exists": os.path.exists(COOKIES_PATH),
        "file_size": os.path.getsize(COOKIES_PATH) if os.path.exists(COOKIES_PATH) else 0,
        "proxy_configured": PROXY_SERVER is not None,
    }


@app.get("/debug-screenshot")
def debug_screenshot():
    if not os.path.exists("debug_screenshot.png"):
        raise HTTPException(status_code=404, detail="Aucun screenshot disponible")
    return FileResponse("debug_screenshot.png")


@app.get("/debug-screenshot-recherche")
def debug_screenshot_recherche():
    if not os.path.exists("debug_screenshot_recherche.png"):
        raise HTTPException(status_code=404, detail="Aucun screenshot disponible")
    return FileResponse("debug_screenshot_recherche.png")


@app.get("/debug-screenshot-avant-validation")
def debug_screenshot_avant_validation():
    if not os.path.exists("debug_screenshot_avant_validation.png"):
        raise HTTPException(status_code=404, detail="Aucun screenshot disponible")
    return FileResponse("debug_screenshot_avant_validation.png")


@app.get("/debug-screenshot-livraison")
def debug_screenshot_livraison():
    if not os.path.exists("debug_screenshot_livraison.png"):
        raise HTTPException(status_code=404, detail="Aucun screenshot disponible")
    return FileResponse("debug_screenshot_livraison.png")


# ---------------------------------------------------------------------
# ÉTAPE 1 :
# ---------------------------------------------------------------------
@app.post("/session/panier")
def build_cart(payload: dict, x_api_key: str = Header(...)):
    check_auth(x_api_key)
    produits = payload["produits"]
    session_id = str(uuid.uuid4())

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            proxy=get_proxy_config(),
            # Render's free instance is 512MB RAM / 0.1 CPU -- these flags
            # trim Chromium's memory footprint to fit that constraint.
            args=["--disable-dev-shm-usage", "--disable-gpu", "--no-sandbox"],
        )
        context = browser.new_context(
            storage_state=COOKIES_PATH if os.path.exists(COOKIES_PATH) else None,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        stealth = Stealth()
        page = context.new_page()
        stealth.apply_stealth_sync(page)

        try:
            page.goto("https://www.marjane.ma/", wait_until="networkidle")
            page.screenshot(path="debug_screenshot.png")

            try:
                page.wait_for_selector("[data-test='my-account-link']", timeout=10000)
            except PWTimeoutError:
                raise HTTPException(
                    status_code=401,
                    detail="Session Marjane expirée ou non connectée, régénérez storage_state.json"
                )

            # Recherche et ajout des produits
            for produit in produits:
                page.fill("input[placeholder='Rechercher un produit ']", produit["nom"])
                page.keyboard.press("Enter")
                page.wait_for_selector("[data-test='add-to-cart-button']", timeout=10000)
                page.screenshot(path="debug_screenshot_recherche.png")

                carte = page.locator("li", has=page.locator(f"h2:has-text('{produit['nom']}')"))
                bouton_ajouter = carte.locator("[data-test='add-to-cart-button']").first

                for _ in range(produit["quantite"]):
                    bouton_ajouter.click()
                    page.wait_for_timeout(500)

            # On va voir le panier, SANS cliquer sur "Valider mon panier"
            page.goto("https://www.marjane.ma/cart")
            page.wait_for_timeout(2000)
            page.screenshot(path="debug_screenshot_avant_validation.png")

            # Lecture du total directement sur la page panier
            total = page.text_content(".fee--big")

            context.storage_state(path=COOKIES_PATH)

        except PWTimeoutError as e:
            raise HTTPException(status_code=502, detail=f"Étape du panier a échoué : {e}")
        finally:
            browser.close()

    return {
        "session_id": session_id,
        "total": total.strip() if total else "N/A",
        "articles": produits,
    }


# ---------------------------------------------------------------------
# ÉTAPE 2
# ---------------------------------------------------------------------
@app.post("/session/pay")
def finalize_payment(x_api_key: str = Header(...)):
    check_auth(x_api_key)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            proxy=get_proxy_config(),
            # Render's free instance is 512MB RAM / 0.1 CPU -- these flags
            # trim Chromium's memory footprint to fit that constraint.
            args=["--disable-dev-shm-usage", "--disable-gpu", "--no-sandbox"],
        )
        context = browser.new_context(storage_state=COOKIES_PATH)
        stealth = Stealth()
        page = context.new_page()
        stealth.apply_stealth_sync(page)

        try:
            page.goto("https://www.marjane.ma/cart")
            page.wait_for_timeout(2000)

            page.wait_for_selector("[data-test='validate-cart-button']", timeout=15000)
            page.click("[data-test='validate-cart-button']")

            # Choix d'adresse (optionnel, peut déjà être pré-sélectionnée)
            try:
                page.wait_for_selector("[data-test='choose-delivery-address-button']", timeout=5000)
                page.click("[data-test='choose-delivery-address-button']")
                page.wait_for_selector("[data-test='select-existing-address']", timeout=10000)
                page.locator("[data-test='select-existing-address']").first.click()
            except PWTimeoutError:
                pass

            page.screenshot(path="debug_screenshot_livraison.png")

            # Choix express (optionnel, peut déjà être pré-sélectionné)
            try:
                page.wait_for_selector("[data-test='choose-delivery-express-button']", timeout=5000)
                page.click("[data-test='choose-delivery-express-button']")
            except PWTimeoutError:
                pass

            page.wait_for_selector("[data-test='validate-checkout-button']", timeout=10000)
            page.click("[data-test='validate-checkout-button']")

            # TODO(pending real selectors from a manual test order -- see chat):
            # these two placeholders were never filled in with real CSS/data-test
            # selectors, so this step currently ALWAYS times out and raises a 502
            # even when the order was successfully placed and paid for above.
            # That means n8n never sees success, "Commande validée" never fires,
            # and a retry after a false failure risks placing/paying for the
            # order a second time. Do not deploy this endpoint for real use
            # until these two lines point at real selectors.
            page.wait_for_selector("SELECTEUR_CONFIRMATION_COMMANDE", timeout=20000)
            numero_commande = page.text_content("SELECTEUR_NUMERO_COMMANDE")

            context.storage_state(path=COOKIES_PATH)

        except PWTimeoutError as e:
            raise HTTPException(status_code=502, detail=f"Étape du paiement a échoué : {e}")
        finally:
            browser.close()

    return {"numero_commande": numero_commande.strip() if numero_commande else "Inconnu"}
