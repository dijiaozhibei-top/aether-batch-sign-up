import asyncio
import logging
from typing import Optional

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

TURNSTILE_SITE_KEY = "0x4AAAAAACzc2OvvV_ueC81i"
REGISTER_URL = "https://to-aether.com/register"


async def _get_token_async(timeout: int = 120) -> Optional[str]:
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

        try:
            logger.info(f"Navigating to {REGISTER_URL}...")
            await page.goto(REGISTER_URL, wait_until="domcontentloaded", timeout=60000)
            logger.info("Page loaded, waiting for Turnstile...")

            for i in range(timeout):
                title = await page.title()

                if title.startswith("TS_TOKEN_"):
                    token = title[len("TS_TOKEN_") :]
                    logger.info(f"Turnstile token acquired ({len(token)} chars)")
                    return token

                # Try to extract token via JavaScript
                try:
                    token = await page.evaluate("window._turnstile_token || ''")
                    if token:
                        logger.info(f"Turnstile token from JS ({len(token)} chars)")
                        return token
                except Exception:
                    pass

                # Click Turnstile checkbox if visible
                if i == 5 or i == 15:
                    try:
                        frame = page.frame_locator(
                            "iframe[src*='challenges.cloudflare.com']"
                        )
                        cb = frame.locator("#challenge-stage input[type=checkbox]")
                        if await cb.is_visible(timeout=3000):
                            logger.info("Clicking Turnstile checkbox...")
                            await cb.click()
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


def solve_turnstile(timeout: int = 120) -> Optional[str]:
    return asyncio.run(_get_token_async(timeout))
