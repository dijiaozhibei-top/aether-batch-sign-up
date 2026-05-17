import asyncio
import logging
import os
import tempfile
from typing import Optional

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

TURNSTILE_SITE_KEY = "0x4AAAAAACzc2OvvV_ueC81i"

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
<div id="turnstile-container"></div>
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
<script>
window.onload = function() {
  turnstile.render('#turnstile-container', {
    sitekey: '%s',
    callback: function(token) {
      document.title = 'TS_TOKEN_' + token;
    },
    'error-callback': function(e) {
      document.title = 'TS_ERROR_' + JSON.stringify(e);
    }
  });
};
</script>
</body>
</html>
"""


async def _get_token_async(timeout: int = 120) -> Optional[str]:
    html = HTML_TEMPLATE % TURNSTILE_SITE_KEY

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False)
    tmp.write(html)
    tmp.close()
    file_url = "file://" + tmp.name

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
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

        try:
            await page.goto(file_url, wait_until="domcontentloaded", timeout=15000)
            logger.info("Local page loaded, waiting for Turnstile...")

            for i in range(timeout):
                title = await page.title()

                if title.startswith("TS_TOKEN_"):
                    token = title[len("TS_TOKEN_") :]
                    logger.info(f"Turnstile token acquired ({len(token)} chars)")
                    return token

                if title.startswith("TS_ERROR_"):
                    logger.warning(f"Turnstile error: {title}")

                # Check for managed challenge iframe (interactive checkbox)
                if i == 5:
                    try:
                        frame = page.frame_locator(
                            "iframe[src*='challenges.cloudflare.com']"
                        )
                        cb = frame.locator("#challenge-stage input[type=checkbox]")
                        if await cb.is_visible(timeout=3000):
                            logger.info("Clicking Turnstile checkbox...")
                            await cb.click()
                            # Move mouse after click for realism
                            await page.mouse.move(500, 500)
                    except Exception:
                        pass

                await asyncio.sleep(1)

            logger.warning("Turnstile did not resolve within timeout")
            return None
        except Exception as e:
            logger.warning(f"Turnstile solve failed: {e}")
            return None
        finally:
            await browser.close()
            try:
                os.unlink(tmp.name)
            except OSError:
                pass


def solve_turnstile(timeout: int = 120) -> Optional[str]:
    return asyncio.run(_get_token_async(timeout))
