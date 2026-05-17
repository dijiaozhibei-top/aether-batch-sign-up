"""
Manual Turnstile token helper.

Opens the Aether registration page in your default browser.
Once Turnstile completes, the token is printed to stdout.

Usage:
    python src/get_turnstile.py

Then copy the token and set it:
    export TURNSTILE_TOKEN="<token>"
"""

import asyncio
import sys
import json
from playwright.async_api import async_playwright


async def get_token():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        await page.goto(
            "https://to-aether.com/register",
            wait_until="networkidle",
        )
        print(
            "Page opened. Please complete the Turnstile in the browser...",
            file=sys.stderr,
        )

        # Fill dummy values to enable the form
        await page.fill("#email", "temp@test.com")
        await page.fill("#password", "TempPass123!")

        try:
            await page.wait_for_function(
                """() => {
                    const inp = document.querySelector(
                        'input[name="cf-turnstile-response"]'
                    );
                    return inp && inp.value && inp.value.length > 20;
                }""",
                timeout=120000,
            )
            token = await page.evaluate(
                """() => document.querySelector(
                    'input[name="cf-turnstile-response"]'
                ).value"""
            )
            print(f"\n=== TURNSTILE TOKEN ===", file=sys.stderr)
            print(f"Token obtained! Length: {len(token)}", file=sys.stderr)
            print(f"\n{token}")
            print(f"\n=== COPY THE ABOVE LINE (without quotes) ===", file=sys.stderr)
            print(f"Set it as:\n  export TURNSTILE_TOKEN='{token}'", file=sys.stderr)
            print(f"\nOr add to .env:\n  TURNSTILE_TOKEN={token}", file=sys.stderr)
            return token
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return None
        finally:
            await browser.close()


def main():
    token = asyncio.run(get_token())
    if token:
        # Print only the token to stdout for piping
        print(token)


if __name__ == "__main__":
    main()
