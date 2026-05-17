import asyncio
import logging
import os
from typing import Optional

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

REGISTER_URL = "https://to-aether.com/register"
SCREENSHOT_DIR = "/tmp/ts_debug"

STEALTH_SCRIPT = """
// Override navigator.webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => false });

// Override chrome.runtime
window.chrome = { runtime: { connect: () => {} } };

// Override permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (p) => (
  p.name === 'notifications' ? Promise.reject({}) : originalQuery(p)
);

// Add plugins
Object.defineProperty(navigator, 'plugins', {
  get: () => [1, 2, 3, 4, 5],
});
Object.defineProperty(navigator, 'languages', {
  get: () => ['en-US', 'en'],
});
"""


async def _try_click_turnstile(page) -> bool:
    """Try to click Turnstile checkbox in iframe."""
    for f in page.frames:
        if "challenges.cloudflare.com" in f.url and "turnstile" in f.url:
            try:
                # Try various selectors for the checkbox
                selectors = [
                    "#challenge-stage input[type=checkbox]",
                    "#cf-challenge input[type=checkbox]",
                    "input[type=checkbox]",
                    "#checkbox",
                    "[role=checkbox]",
                    ".challenge-button",
                    "#challenge-stage label",
                ]
                for sel in selectors:
                    try:
                        cb = f.locator(sel)
                        if await cb.is_visible(timeout=2000):
                            logger.info(f"Clicking Turnstile checkbox ({sel})")
                            await cb.click(timeout=3000)
                            await asyncio.sleep(0.5)
                            return True
                    except Exception:
                        continue

                # Try clicking via JS inside iframe
                logger.info("Trying JS click inside Turnstile iframe")
                await f.evaluate("""
                    () => {
                        const cb = document.querySelector('input[type=checkbox]');
                        if (cb) { cb.click(); return 'clicked'; }
                        const labels = document.querySelectorAll('label');
                        for (const l of labels) { if (l.offsetParent !== null) { l.click(); return 'label_clicked'; } }
                        return 'no_element';
                    }
                """)
                return True
            except Exception as e:
                logger.warning(f"Iframe interaction error: {e}")
    return False


async def _get_token_async(timeout: int = 120) -> Optional[str]:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )
        page = await context.new_page()
        await page.add_init_script(STEALTH_SCRIPT)

        page.on("console", lambda msg: logger.debug(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: logger.debug(f"PAGE_ERR: {err}"))

        try:
            logger.info(f"Navigating to {REGISTER_URL}...")
            await page.goto(REGISTER_URL, wait_until="domcontentloaded", timeout=60000)
            logger.info("Page loaded")

            await page.screenshot(path=f"{SCREENSHOT_DIR}/01_loaded.png")
            page_html = await page.content()
            logger.info(f"HTML length: {len(page_html)}")
            with open(f"{SCREENSHOT_DIR}/page.html", "w") as f:
                f.write(page_html[:50000])

            # Wait for Turnstile iframe to appear
            for _ in range(15):
                has_ts = any(
                    "challenges.cloudflare.com" in f.url and "turnstile" in f.url
                    for f in page.frames
                )
                if has_ts:
                    logger.info("Turnstile iframe detected")
                    break
                await asyncio.sleep(1)
            else:
                logger.warning("Turnstile iframe never appeared")

            iframes_info = [f.url for f in page.frames]
            logger.info(
                f"Frames ({len(iframes_info)}): {[u[:100] for u in iframes_info]}"
            )

            for i in range(timeout):
                # Check for token in page title (set by widgets callback)
                title = await page.title()
                if title and "TS_TOKEN_" in title:
                    token = title.split("TS_TOKEN_")[1]
                    logger.info(f"Token from title ({len(token)} chars)")
                    return token

                # Check via JS
                try:
                    token = await page.evaluate("""
                        () => {
                            if (window._turnstile_token) return window._turnstile_token;
                            const el = document.querySelector('.cf-turnstile');
                            if (el) {
                                if (el._token) return el._token;
                                if (el.firstChild && el.firstChild._token) return el.firstChild._token;
                            }
                            try {
                                const r = turnstile.getResponse();
                                if (r) return r;
                            } catch(e) {}
                            return '';
                        }
                    """)
                    if token:
                        logger.info(f"Turnstile token from JS ({len(token)} chars)")
                        return token
                except Exception:
                    pass

                # Interaction attempts
                if i in (3, 10, 20, 30):
                    logger.info(f"Interaction attempt at i={i}")
                    clicked = await _try_click_turnstile(page)
                    if not clicked:
                        logger.info("No checkbox found, trying widget div click")
                        try:
                            widget = page.locator(
                                "#turnstile-widget, .cf-turnstile, "
                                "[class*='turnstile'], iframe[src*='challenges']"
                            )
                            if await widget.is_visible(timeout=2000):
                                await widget.click(timeout=3000)
                                await page.mouse.move(500, 500)
                                logger.info("Clicked widget div")
                        except Exception:
                            pass

                # Screenshot every 20 seconds for debugging
                if i % 20 == 0:
                    try:
                        await page.screenshot(
                            path=f"{SCREENSHOT_DIR}/state_{i:03d}.png"
                        )
                    except Exception:
                        pass

                await asyncio.sleep(1)

            logger.warning("Turnstile did not resolve within timeout")
            await page.screenshot(path=f"{SCREENSHOT_DIR}/99_timeout.png")
            return None
        except Exception as e:
            logger.warning(f"Turnstile solve failed: {e}")
            try:
                await page.screenshot(path=f"{SCREENSHOT_DIR}/99_error.png")
            except Exception:
                pass
            return None
        finally:
            await browser.close()


def solve_turnstile(timeout: int = 120) -> Optional[str]:
    return asyncio.run(_get_token_async(timeout))
