import asyncio
import logging
import os
from typing import Optional

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

REGISTER_URL = "https://to-aether.com/register"
SCREENSHOT_DIR = "/tmp/ts_debug"


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

        page.on("console", lambda msg: logger.debug(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: logger.debug(f"PAGE_ERR: {err}"))

        try:
            logger.info(f"Navigating to {REGISTER_URL}...")
            await page.goto(REGISTER_URL, wait_until="domcontentloaded", timeout=60000)
            logger.info("Page loaded")

            await page.screenshot(path=f"{SCREENSHOT_DIR}/01_loaded.png")
            html_preview = await page.content()
            logger.info(f"Page HTML length: {len(html_preview)}")
            with open(f"{SCREENSHOT_DIR}/page.html", "w") as f:
                f.write(html_preview[:50000])

            iframes = page.frames
            logger.info(f"Frames: {len(iframes)}")
            for f in iframes:
                logger.info(f"  Frame: {f.url[:120]}")

            for i in range(timeout):
                # Try to extract token via turnstile.getResponse
                try:
                    token = await page.evaluate(
                        """() => {
                            const el = document.querySelector('.cf-turnstile');
                            if (el && el._token) return el._token;
                            if (window.turnstile) {
                                const resp = turnstile.getResponse();
                                if (resp) return resp;
                            }
                            return '';
                        }"""
                    )
                    if token:
                        logger.info(
                            f"Turnstile token from page JS ({len(token)} chars)"
                        )
                        return token
                except Exception:
                    pass

                # Click actions at various intervals
                if i in (3, 8, 15, 25):
                    # Strategy 1: Click the cf-turnstile widget div directly
                    try:
                        widget = page.locator(
                            "#turnstile-widget, .cf-turnstile, [class*='turnstile']"
                        )
                        if await widget.is_visible(timeout=2000):
                            logger.info("Clicking Turnstile widget div...")
                            await widget.click(timeout=3000)
                            await page.mouse.move(500, 500)
                            continue
                    except Exception:
                        pass

                    # Strategy 2: Click checkbox in any iframe from challenges.cloudflare.com
                    try:
                        ts_frame = None
                        for f in page.frames:
                            if "challenges.cloudflare.com" in f.url:
                                ts_frame = f
                                break
                        if ts_frame:
                            logger.info(f"Found Turnstile frame: {ts_frame.url}")
                            cb = ts_frame.locator(
                                "#challenge-stage input[type=checkbox], "
                                "#cf-challenge input[type=checkbox], "
                                "[aria-label*='challenge'], "
                                "#checkbox"
                            )
                            if await cb.is_visible(timeout=3000):
                                logger.info("Clicking checkbox in Turnstile iframe...")
                                await cb.click(timeout=3000)
                                await page.mouse.move(500, 500)
                    except Exception:
                        pass

                    # Strategy 3: Try injecting JS to execute turnstile
                    try:
                        result = await page.evaluate(
                            """() => {
                                if (window.turnstile && typeof turnstile.execute === 'function') {
                                    turnstile.execute('0x4AAAAAACzc2OvvV_ueC81i', {
                                        callback: function(token) {
                                            window._turnstile_token = token;
                                            document.title = 'TS_TOKEN_' + token;
                                        }
                                    });
                                    return 'executed';
                                }
                                if (window.turnstile && typeof turnstile.render === 'function') {
                                    turnstile.render('#turnstile-widget', {
                                        sitekey: '0x4AAAAAACzc2OvvV_ueC81i',
                                        callback: function(token) {
                                            window._turnstile_token = token;
                                            document.title = 'TS_TOKEN_' + token;
                                        }
                                    });
                                    return 'rendered';
                                }
                                return 'no_turnstile';
                            }"""
                        )
                        logger.info(f"JS turnstile execute: {result}")
                    except Exception as e:
                        logger.warning(f"JS turnstile execute error: {e}")

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
