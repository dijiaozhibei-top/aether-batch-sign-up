import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

REGISTER_URL = "https://to-aether.com/register"
SCREENSHOT_DIR = "/tmp/ts_debug"


def solve_turnstile(timeout: int = 120) -> Optional[str]:
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

        driver.get(REGISTER_URL)
        logger.info(f"Navigated to {REGISTER_URL}")

        driver.save_screenshot(f"{SCREENSHOT_DIR}/01_loaded.png")
        with open(f"{SCREENSHOT_DIR}/page.html", "w") as f:
            f.write(driver.page_source[:50000])

        logger.info(f"Page title: {driver.title}")
        logger.info(f"Frames: {len(driver.window_handles)}")

        deadline = time.time() + timeout
        while time.time() < deadline:
            # Check for token in localStorage / sessionStorage / window
            try:
                token = driver.execute_script("""
                    try {
                        var r = turnstile.getResponse();
                        if (r) return r;
                    } catch(e) {}
                    var el = document.querySelector('.cf-turnstile');
                    if (el && el._token) return el._token;
                    return '';
                """)
                if token:
                    logger.info(f"Turnstile token acquired ({len(token)} chars)")
                    return token
            except Exception:
                pass

            # Check if Turnstile iframe has a checkbox and click it
            try:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    src = iframe.get_attribute("src") or ""
                    if "challenges.cloudflare.com" in src and "turnstile" in src:
                        logger.info(f"Found Turnstile iframe, trying interaction")
                        driver.switch_to.frame(iframe)
                        try:
                            for sel in [
                                "input[type=checkbox]",
                                "#challenge-stage input",
                                "[role=checkbox]",
                                ".challenge-button",
                            ]:
                                els = driver.find_elements(By.CSS_SELECTOR, sel)
                                for el in els:
                                    if el.is_displayed():
                                        logger.info(f"Clicking: {sel}")
                                        el.click()
                                        time.sleep(0.5)
                                        break
                        finally:
                            driver.switch_to.default_content()
                        break
            except Exception:
                pass

            time.sleep(1)

        logger.warning("Turnstile did not resolve within timeout")
        driver.save_screenshot(f"{SCREENSHOT_DIR}/99_timeout.png")
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
