"""
Playwright-based Aether registration script.
Opens the registration page in a real browser, fills in the form,
waits for Turnstile, reads email code from Gmail, and completes registration.
"""

import asyncio
import logging
import json
import re
import time
from typing import Optional

from playwright.async_api import async_playwright, Page

from src.config import settings
from src.gmail_pop3 import GmailPop3Client

logger = logging.getLogger(__name__)


async def playwright_register(page: Page, email: str, password: str) -> Optional[str]:
    """
    Use Playwright to go through the full registration flow.
    Returns the access token on success, or None.
    """
    logger.info(f"Playwright: registering {email}")

    await page.goto(
        f"{settings.aether_base_url}/register",
        wait_until="networkidle",
    )
    await asyncio.sleep(2)

    # Fill email and password
    await page.fill("#email", email)
    await page.fill("#password", password)

    # Wait for Turnstile to complete
    logger.info("Waiting for Turnstile to complete...")
    try:
        await page.wait_for_function(
            """() => {
                const inp = document.querySelector(
                    'input[name="cf-turnstile-response"]'
                );
                return inp && inp.value && inp.value.length > 20;
            }""",
            timeout=60000,
        )
        logger.info("Turnstile completed!")
    except Exception:
        logger.warning("Turnstile did not auto-complete, trying to click...")
        # Try clicking the turnstile widget
        try:
            turnstile_frame = page.frame_locator(
                "iframe[src*='challenges.cloudflare.com']"
            )
            await turnstile_frame.locator("input[type='checkbox']").click(timeout=5000)
            await asyncio.sleep(3)
        except Exception:
            logger.error("Could not solve Turnstile automatically")
            return None

    # Click submit
    submit_btn = page.locator('button[type="submit"]')
    await submit_btn.wait_for(state="visible", timeout=10000)

    # Check if button is still disabled (turnstile not solved)
    is_disabled = await submit_btn.is_disabled()
    if is_disabled:
        # Try to get the turnstile token from the page
        turnstile_token = await page.evaluate(
            """() => document.querySelector(
                'input[name="cf-turnstile-response"]'
            )?.value || ''"""
        )
        if not turnstile_token:
            logger.error("Turnstile not solved, button still disabled")
            return None

    await submit_btn.click()

    # Wait for navigation to email-verify page
    try:
        await page.wait_for_url("**/email-verify", timeout=15000)
        logger.info("Navigated to email-verify page")
    except Exception:
        logger.error("Did not navigate to email-verify page")
        return None

    # Get verification code from Gmail
    logger.info("Waiting for verification code from Gmail...")
    with GmailPop3Client(
        email_address=settings.gmail_email,
        app_password=settings.gmail_app_password,
        host=settings.gmail_pop3_host,
        port=settings.gmail_pop3_port,
    ) as pop3:
        code = pop3.wait_for_verification_code(
            expected_email=email,
            timeout=120,
            interval=5,
        )

    if not code:
        logger.error("Failed to get verification code")
        return None

    logger.info(f"Got verification code: {code}")

    # Fill in verification code
    code_input = page.locator("#code")
    await code_input.wait_for(state="visible", timeout=10000)
    await code_input.fill(code)

    # Wait for Turnstile on verify page (may be needed)
    await asyncio.sleep(2)

    # Click verify button
    verify_btn = page.locator('button[type="submit"]')
    await verify_btn.wait_for(state="visible", timeout=10000)
    await verify_btn.click()

    # Wait for navigation to dashboard or login
    try:
        await page.wait_for_url("**/dashboard", timeout=30000)
        logger.info("Registration completed! Navigated to dashboard")

        # Get the access token from localStorage
        token = await page.evaluate("""() => localStorage.getItem('auth_token')""")
        return token
    except Exception:
        logger.warning("Did not navigate to dashboard, trying login...")
        return None


async def playwright_login(page: Page, email: str, password: str) -> Optional[str]:
    """Login and return access token."""
    await page.goto(
        f"{settings.aether_base_url}/login",
        wait_until="networkidle",
    )
    await asyncio.sleep(2)

    await page.fill("#email", email)
    await page.fill("#password", password)

    # Wait for Turnstile
    try:
        await page.wait_for_function(
            """() => {
                const inp = document.querySelector(
                    'input[name="cf-turnstile-response"]'
                );
                return inp && inp.value && inp.value.length > 20;
            }""",
            timeout=60000,
        )
    except Exception:
        logger.warning("Turnstile did not auto-complete on login")

    submit_btn = page.locator('button[type="submit"]')
    await submit_btn.wait_for(state="visible", timeout=10000)
    await submit_btn.click()

    try:
        await page.wait_for_url("**/dashboard", timeout=30000)
        token = await page.evaluate("""() => localStorage.getItem('auth_token')""")
        return token
    except Exception:
        logger.error("Login failed")
        return None


async def playwright_create_api_keys(page: Page) -> list:
    """Create API keys for all available groups via Playwright."""
    await page.goto(
        f"{settings.aether_base_url}/keys",
        wait_until="networkidle",
    )
    await asyncio.sleep(3)

    # Get groups from the API
    from src.aether_api import AetherAPI

    api = AetherAPI(settings.aether_api_base)

    token = await page.evaluate("""() => localStorage.getItem('auth_token')""")
    if token:
        api._access_token = token
        api._update_auth_header()

    groups = api.get_available_groups()
    target_names = settings.target_group_list
    created_keys = []

    for group in groups:
        gid = group.get("id")
        gname = group.get("name", "unknown")
        gplatform = group.get("platform", "unknown")

        if target_names and gname not in target_names:
            continue

        key_name = f"auto-{gname}-{int(time.time())}"

        try:
            result = api.create_api_key(
                name=key_name,
                group_id=gid,
            )
            key_value = result.get("key", result)
            created_keys.append(
                {
                    "group_name": gname,
                    "group_id": gid,
                    "platform": gplatform,
                    "key_name": key_name,
                    "key_value": key_value,
                }
            )
            logger.info(f"Created API key for group '{gname}'")
        except Exception as e:
            logger.error(f"Failed to create key for '{gname}': {e}")

    api.close()
    return created_keys


async def run_batch_playwright() -> list:
    """Run batch registration using Playwright."""
    accounts = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
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

        for idx in range(settings.batch_start, settings.batch_end + 1):
            email = f"{settings.account_email_base}+{idx}@gmail.com"
            password = settings.account_password

            logger.info(f"\n{'=' * 60}")
            logger.info(f"Processing account #{idx}: {email}")
            logger.info(f"{'=' * 60}")

            # Register
            token = await playwright_register(page, email, password)
            if not token:
                logger.error(f"Registration failed for {email}")
                continue

            # Create API keys
            keys = await playwright_create_api_keys(page)

            accounts.append(
                {
                    "email": email,
                    "password": password,
                    "access_token": token,
                    "api_keys": keys,
                }
            )

            logger.info(f"Account {email}: {len(keys)} API key(s) created")

        await browser.close()

    return accounts


async def main_async():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("Starting Aether batch registration (Playwright mode)...")

    accounts = await run_batch_playwright()

    print("\n\n" + "=" * 60)
    print("  BATCH REGISTRATION SUMMARY")
    print("=" * 60)
    print(f"  Accounts registered: {len(accounts)}\n")

    for acc in accounts:
        print(f"  [{acc['email']}]")
        for key in acc.get("api_keys", []):
            print(f"    {key['group_name']}: {key['key_value']}")
        print()

    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "accounts": accounts,
    }
    for acc in output["accounts"]:
        acc.pop("access_token", None)

    with open("aether_accounts.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"  Results saved to: aether_accounts.json")
    print("=" * 60)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
