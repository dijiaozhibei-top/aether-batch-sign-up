import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

REGISTER_URL = "https://to-aether.com/register"
SCREENSHOT_DIR = "/tmp/ts_debug"


def solve_turnstile(timeout: int = 60) -> Optional[str]:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,800")

    driver = None
    try:
        driver = uc.Chrome(options=options, headless=False)
        logger.info("undetected-chromedriver started")

        driver.set_page_load_timeout(30)
        driver.get(REGISTER_URL)
        logger.info(f"Page loaded, title: {driver.title}")
        time.sleep(2)

        driver.save_screenshot(f"{SCREENSHOT_DIR}/01_loaded.png")

        # Render Turnstile on the existing hidden input
        logger.info("Calling turnstile.render()...")
        render_result = driver.execute_script("""
            var inp = document.querySelector('input[name="cf-turnstile-response"]');
            if (!inp) {
                inp = document.createElement('input');
                inp.type = 'hidden';
                inp.name = 'cf-turnstile-response';
                document.body.appendChild(inp);
            }
            var wid = turnstile.render(inp, {
                sitekey: '0x4AAAAAACzc2OvvV_ueC81i',
                callback: function(token) {
                    inp.value = token;
                    window._turnstile_token = token;
                    document.title = 'TS_TOKEN_' + token;
                },
                'error-callback': function(e) {
                    document.title = 'TS_ERROR_' + JSON.stringify(e);
                }
            });
            return 'widget_' + wid;
        """)

        logger.info(f"Render result: {render_result}")
        time.sleep(2)

        # Execute the widget
        logger.info("Calling turnstile.execute()...")
        exec_result = driver.execute_script("""
            var inp = document.querySelector('input[name="cf-turnstile-response"]');
            var wid = inp ? inp.getAttribute('data-widget-id') : null;
            try {
                var result = turnstile.execute(wid || inp);
                return 'execute_ok_' + (result || '');
            } catch(e) {
                return 'execute_err_' + e.message;
            }
        """)
        logger.info(f"Execute result: {exec_result}")

        # Wait for callback
        deadline = time.time() + timeout
        while time.time() < deadline:
            title = driver.title
            if "TS_TOKEN_" in title:
                token = title.split("TS_TOKEN_")[1]
                logger.info(f"Token from title ({len(token)} chars)")
                driver.save_screenshot(f"{SCREENSHOT_DIR}/99_success.png")
                return token

            if "TS_ERROR_" in title:
                logger.warning(f"Turnstile error: {title}")

            # Also check via JS
            try:
                token = driver.execute_script(
                    "return document.querySelector('input[name=\"cf-turnstile-response\"]')?.value || '';"
                )
                if token:
                    logger.info(f"Token from hidden input ({len(token)} chars)")
                    return token
            except Exception:
                pass

            time.sleep(1)

        logger.warning("Turnstile did not resolve within timeout")
        driver.save_screenshot(f"{SCREENSHOT_DIR}/99_timeout.png")
        with open(f"{SCREENSHOT_DIR}/page.html", "w") as f:
            f.write(driver.page_source[:100000])
        return None

    except Exception as e:
        logger.warning(f"Turnstile solve failed: {e}")
        try:
            if driver:
                driver.save_screenshot(f"{SCREENSHOT_DIR}/99_error.png")
        except Exception:
            pass
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
