import asyncio
import logging
from typing import Optional

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


async def _get_token_async(page_url: str, timeout: int = 45) -> Optional[str]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            await page.goto(page_url, wait_until="networkidle", timeout=30000)
            logger.info("Page loaded, waiting for Turnstile to resolve...")

            token = await page.wait_for_function(
                """() => {
                    const el = document.querySelector('input[name="cf-turnstile-response"]');
                    if (el && el.value && el.value.length > 20) return el.value;
                    const widget = document.querySelector('.cf-turnstile');
                    if (widget && widget.getAttribute('data-token')) return widget.getAttribute('data-token');
                    return null;
                }""",
                timeout=timeout * 1000,
            )
            result = await token.json_value()
            if result:
                logger.info(f"Turnstile token acquired ({len(result)} chars)")
                return result

            logger.warning("Turnstile did not resolve automatically")
            return None
        except Exception as e:
            logger.warning(f"Turnstile solve failed: {e}")
            return None
        finally:
            await browser.close()


def solve_turnstile(page_url: str, timeout: int = 45) -> Optional[str]:
    return asyncio.run(_get_token_async(page_url, timeout))
