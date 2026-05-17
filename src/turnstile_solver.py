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
    from selenium.webdriver.common.keys import Keys

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
        logger.info(f"Page loaded, title: {driver.title}")

        driver.save_screenshot(f"{SCREENSHOT_DIR}/01_loaded.png")
        with open(f"{SCREENSHOT_DIR}/page.html", "w") as f:
            f.write(driver.page_source[:100000])

        deadline = time.time() + timeout
        clicked = False

        while time.time() < deadline:
            # 1. Try extracting token from page
            try:
                token = driver.execute_script("""
                    try {
                        var r = turnstile.getResponse();
                        if (r) return r;
                    } catch(e) {}
                    var el = document.querySelector('.cf-turnstile input[name="cf-turnstile-response"]');
                    if (el && el.value) return el.value;
                    var inp = document.querySelector("[name='cf-turnstile-response']");
                    if (inp && inp.value) return inp.value;
                    return '';
                """)
                if token:
                    logger.info(f"Turnstile token acquired ({len(token)} chars)")
                    return token
            except Exception:
                pass

            # 2. Wait for iframe and click checkbox
            try:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    src = iframe.get_attribute("src") or ""
                    if "challenges.cloudflare.com" in src and "turnstile" in src:
                        driver.switch_to.frame(iframe)
                        try:
                            for sel in [
                                "input[type=checkbox]",
                                "[role=checkbox]",
                                "#challenge-stage input",
                                ".challenge-button",
                                "label",
                            ]:
                                els = driver.find_elements(By.CSS_SELECTOR, sel)
                                for el in els:
                                    if el.is_displayed() and el.is_enabled():
                                        logger.info(f"Clicking iframe element: {sel}")
                                        driver.execute_script(
                                            "arguments[0].click();", el
                                        )
                                        time.sleep(1)
                                        clicked = True
                                        break
                                if clicked:
                                    break
                        finally:
                            driver.switch_to.default_content()
                        break
            except Exception:
                pass

            # 3. If iframe interaction didn't work, try triggering Turnstile via form
            if not clicked and time.time() > deadline - 60:
                logger.info("Trying to trigger Turnstile via form interaction")
                try:
                    email_input = driver.find_element(
                        By.CSS_SELECTOR, "input[type=email], input[name=email]"
                    )
                    if email_input and email_input.is_displayed():
                        email_input.click()
                        email_input.send_keys("test@example.com")
                        time.sleep(0.5)
                        email_input.clear()
                        time.sleep(0.5)
                        logger.info("Triggered email field interaction")

                    # Try submitting to trigger Turnstile
                    submit_btn = driver.find_element(
                        By.CSS_SELECTOR,
                        "button[type=submit], button:has-text('Send'), button:has-text('Register')",
                    )
                    if submit_btn and submit_btn.is_displayed():
                        logger.info("Clicking submit to trigger Turnstile")
                        driver.execute_script("arguments[0].click();", submit_btn)
                        time.sleep(3)
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
