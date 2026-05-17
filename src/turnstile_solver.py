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
        time.sleep(2)  # Let JS settle

        driver.save_screenshot(f"{SCREENSHOT_DIR}/01_loaded.png")

        # Debug: print Turnstile-related HTML
        try:
            ts_elements = driver.execute_script("""
                // Find all Turnstile-related elements
                var results = [];
                // Check for cf-turnstile div
                var ct = document.querySelector('.cf-turnstile');
                if (ct) {
                    results.push('cf-turnstile div: ' + ct.outerHTML.substring(0, 200));
                    // Check for shadow root
                    if (ct.shadowRoot) results.push('HAS SHADOW ROOT');
                    if (ct.firstChild) results.push('firstChild tag: ' + ct.firstChild.tagName);
                } else {
                    results.push('NO .cf-turnstile div found');
                }
                // Check for turnstile in window
                results.push('window.turnstile: ' + (typeof window.turnstile));
                if (window.turnstile) {
                    results.push('turnstile.render: ' + (typeof window.turnstile.render));
                    results.push('turnstile.execute: ' + (typeof window.turnstile.execute));
                    results.push('turnstile.getResponse: ' + (typeof window.turnstile.getResponse));
                }
                // Check for hidden inputs
                var inputs = document.querySelectorAll('input[name=\"cf-turnstile-response\"]');
                results.push('cf-turnstile-response inputs: ' + inputs.length);
                // Check for iframes in page
                var ifs = document.querySelectorAll('iframe');
                results.push('iframes: ' + ifs.length);
                for (var i = 0; i < ifs.length && i < 5; i++) {
                    results.push('  iframe[' + i + '] src: ' + (ifs[i].src || '').substring(0, 120));
                }
                return results.join('\\n');
            """)
            for line in ts_elements.split("\n"):
                logger.info(f"TS: {line}")
        except Exception as e:
            logger.warning(f"TS debug error: {e}")

        try:
            with open(f"{SCREENSHOT_DIR}/page.html", "w") as f:
                f.write(driver.page_source[:100000])
        except Exception:
            pass

        deadline = time.time() + timeout
        strategies_tried = set()

        while time.time() < deadline:
            elapsed = int(time.time() - (deadline - timeout))

            # 1. Check for token
            try:
                token = driver.execute_script("""
                    try {
                        var r = turnstile.getResponse();
                        if (r) return r;
                    } catch(e) {}
                    var inp = document.querySelector('input[name="cf-turnstile-response"]');
                    if (inp && inp.value) return inp.value;
                    var el = document.querySelector('.cf-turnstile');
                    if (el && el._token) return el._token;
                    return '';
                """)
                if token:
                    logger.info(f"Turnstile token acquired ({len(token)} chars)")
                    return token
            except Exception:
                pass

            # 2. Try Turnstile checkbox via iframe (every iteration)
            try:
                for iframe in driver.find_elements(By.TAG_NAME, "iframe"):
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
                                    if el.is_displayed():
                                        logger.info(f"Clicking iframe: {sel}")
                                        driver.execute_script(
                                            "arguments[0].click();", el
                                        )
                                        time.sleep(0.5)
                        finally:
                            driver.switch_to.default_content()
                        break
            except Exception:
                pass

            # 3. Execute turnstile.render() on a custom container (strategy 3)
            if 3 not in strategies_tried and elapsed > 3:
                strategies_tried.add(3)
                logger.info("Strategy 3: Injecting Turnstile widget into page")
                try:
                    driver.execute_script("""
                        if (typeof turnstile !== 'undefined' && !document.querySelector('.cf-turnstile')) {
                            var div = document.createElement('div');
                            div.className = 'cf-turnstile';
                            div.id = 'ts-custom';
                            document.body.appendChild(div);
                            turnstile.render('#ts-custom', {
                                sitekey: '0x4AAAAAACzc2OvvV_ueC81i',
                                callback: function(token) {
                                    window._turnstile_token = token;
                                    document.title = 'TS_TOKEN_' + token;
                                }
                            });
                        }
                    """)
                    logger.info("Turnstile render injected, waiting for callback...")
                except Exception as e:
                    logger.warning(f"Strategy 3 failed: {e}")

            # 4. Try turnstile.execute() (strategy 4)
            if 4 not in strategies_tried and elapsed > 8:
                strategies_tried.add(4)
                logger.info("Strategy 4: Calling turnstile.execute()")
                try:
                    result = driver.execute_script("""
                        try {
                            // Try rendering Turnstile on body
                            var inp = document.createElement('input');
                            inp.type = 'hidden';
                            inp.name = 'cf-turnstile-response';
                            document.body.appendChild(inp);
                            turnstile.render(inp, {
                                sitekey: '0x4AAAAAACzc2OvvV_ueC81i',
                                callback: function(token) {
                                    inp.value = token;
                                    window._turnstile_token = token;
                                    document.title = 'TS_TOKEN_' + token;
                                }
                            });
                            return 'rendered on input';
                        } catch(e) {
                            return 'error: ' + e.message;
                        }
                    """)
                    logger.info(f"Strategy 4 result: {result}")
                except Exception as e:
                    logger.warning(f"Strategy 4 failed: {e}")

            # 5. Use the API / submit form to trigger Turnstile
            if 5 not in strategies_tried and elapsed > 20:
                strategies_tried.add(5)
                logger.info("Strategy 5: Filling form and clicking submit")
                try:
                    email_inp = driver.find_element(
                        By.CSS_SELECTOR, "input[type=email]"
                    )
                    if email_inp and email_inp.is_displayed():
                        email_inp.clear()
                        email_inp.send_keys("test@example.com")
                        time.sleep(0.5)
                        pwd_inp = driver.find_element(
                            By.CSS_SELECTOR, "input[type=password]"
                        )
                        if pwd_inp and pwd_inp.is_displayed():
                            pwd_inp.clear()
                            pwd_inp.send_keys("TestPass123!")
                        try:
                            btn = driver.find_element(
                                By.CSS_SELECTOR, "button[type=submit]"
                            )
                            driver.execute_script("arguments[0].click();", btn)
                            logger.info("Clicked submit button")
                        except Exception:
                            pass
                        time.sleep(3)
                except Exception as e:
                    logger.warning(f"Strategy 5 failed: {e}")

            # Screenshot at key moments
            if elapsed in [5, 15, 30, 45]:
                try:
                    driver.save_screenshot(f"{SCREENSHOT_DIR}/state_{elapsed}s.png")
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
