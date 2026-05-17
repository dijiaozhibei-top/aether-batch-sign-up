import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

TURNSTILE_SITE_KEY = "0x4AAAAAACzc2OvvV_ueC81i"


async def _get_token_async(timeout: int = 90) -> Optional[str]:
    try:
        import nodriver as uc
    except ImportError:
        logger.error("nodriver not installed. Run: pip install nodriver")
        return None

    browser = await uc.start()
    page = await browser.get(
        f"https://to-aether.com/register",
        new_window=True,
    )
    try:
        logger.info("Waiting for Turnstile to resolve via nodriver...")

        async def check_token():
            try:
                token = await page.evaluate(
                    """() => {
                        const el = document.querySelector('input[name="cf-turnstile-response"]');
                        if (el && el.value && el.value.length > 20) return el.value;
                        return null;
                    }"""
                )
                return token
            except Exception:
                return None

        for _ in range(timeout):
            token = await check_token()
            if token:
                logger.info(f"Turnstile token acquired ({len(token)} chars)")
                return token
            await asyncio.sleep(1)

        logger.warning("Turnstile did not resolve within timeout")
        return None
    except Exception as e:
        logger.warning(f"Turnstile solve failed: {e}")
        return None
    finally:
        try:
            browser.stop()
        except Exception:
            pass


def solve_turnstile(timeout: int = 90) -> Optional[str]:
    return asyncio.run(_get_token_async(timeout))
