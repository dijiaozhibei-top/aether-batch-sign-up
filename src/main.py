import logging
import json
import time
from typing import Optional, List

from src.config import settings
from src.gmail_pop3 import GmailPop3Client
from src.aether_api import AetherAPI, solve_turnstile_capsolver

logger = logging.getLogger(__name__)


def get_turnstile_token() -> Optional[str]:
    """Get Turnstile token: env var -> CapSolver -> Playwright solver."""
    if settings.turnstile_token:
        logger.info("Using manual Turnstile token from env/config")
        return settings.turnstile_token

    capsolver_key = settings.capsolver_api_key
    if capsolver_key:
        logger.info("Getting Turnstile token via CapSolver...")
        api = AetherAPI(settings.aether_api_base)
        try:
            pub = api.get_public_settings()
            site_key = pub.get("turnstile_site_key", "")
            if site_key:
                token = solve_turnstile_capsolver(
                    site_key=site_key,
                    page_url=f"{settings.aether_base_url}/register",
                    capsolver_key=capsolver_key,
                )
                if token:
                    return token
                logger.warning("CapSolver failed, trying Playwright...")
        finally:
            api.close()

    logger.info("Getting Turnstile token via Playwright browser...")
    from src.turnstile_solver import solve_turnstile

    token = solve_turnstile(timeout=90)
    if token:
        logger.info("Turnstile token obtained via Playwright")
        return token

    logger.error("All Turnstile methods failed")
    return None


def register_one(
    email: str, password: str, turnstile_token: Optional[str]
) -> Optional[dict]:
    """Register a single account and return the register result."""
    api = AetherAPI(settings.aether_api_base)
    try:
        logger.info(f"Sending verification code to {email}...")

        # Check settings for needed parameters
        pub = api.get_public_settings()
        email_verify = pub.get("email_verify_enabled", True)
        ts_enabled = pub.get("turnstile_enabled", False)

        token = turnstile_token if ts_enabled else None

        if email_verify:
            api.send_verify_code(email, turnstile_token=token)
            logger.info("Verification code sent via email.")

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
                logger.error(f"No verification code for {email}")
                return None
            logger.info(f"Verification code: {code}")

            result = api.register(
                email,
                password,
                verify_code=code,
                turnstile_token=token,
            )
        else:
            result = api.register(
                email,
                password,
                turnstile_token=token,
            )

        logger.info(f"Registered: {email}")
        return result
    except Exception as e:
        logger.error(f"Registration failed for {email}: {e}")
        return None
    finally:
        api.close()


def create_api_keys_for_account(api: AetherAPI) -> List[dict]:
    """Create API keys for all (or target) groups."""
    groups = api.get_available_groups()
    target_names = settings.target_group_list
    created = []

    for g in groups:
        gid = g.get("id")
        gname = g.get("name", "unknown")
        gplat = g.get("platform", "unknown")

        if target_names and gname not in target_names:
            continue

        key_name = f"auto-{gname}-{int(time.time())}"
        try:
            result = api.create_api_key(name=key_name, group_id=gid)
            kv = result.get("key", result)
            created.append(
                {
                    "group_name": gname,
                    "group_id": gid,
                    "platform": gplat,
                    "key_name": key_name,
                    "key_value": kv,
                }
            )
            logger.info(f"Key created for '{gname}': {kv}")
        except Exception as e:
            logger.error(f"Key creation failed for '{gname}': {e}")

    return created


def run_batch() -> List[dict]:
    """Batch register accounts and collect API keys."""
    token = get_turnstile_token()
    if token is None:
        logger.error("Failed to get Turnstile token, aborting.")
        return []

    accounts = []

    for idx in range(settings.batch_start, settings.batch_end + 1):
        email = f"{settings.account_email_base}+{idx}@gmail.com"
        password = settings.account_password

        logger.info(f"\n{'=' * 60}")
        logger.info(f"[{idx}/{settings.batch_end}] {email}")
        logger.info(f"{'=' * 60}")

        reg = register_one(email, password, token)
        if not reg:
            logger.error(f"Skipping {email}")
            continue

        # Login + create keys via the logged-in API
        api = AetherAPI(settings.aether_api_base)
        try:
            access = reg.get("access_token")
            if access:
                api._access_token = access
                api._refresh_token = reg.get("refresh_token")
                api._update_auth_header()
            else:
                api.login(email, password, turnstile_token=token)

            keys = create_api_keys_for_account(api)

            accounts.append(
                {
                    "email": email,
                    "password": password,
                    "api_keys": keys,
                }
            )

            logger.info(f"Done: {email} -> {len(keys)} keys")
        except Exception as e:
            logger.error(f"Key creation failed for {email}: {e}")
            accounts.append(
                {
                    "email": email,
                    "password": password,
                    "api_keys": [],
                    "error": str(e),
                }
            )
        finally:
            api.close()

        # Wait between registrations
        if idx < settings.batch_end:
            wait = settings.register_interval
            logger.info(f"Waiting {wait}s before next registration...")
            time.sleep(wait)

    return accounts


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    start, end = settings.batch_start, settings.batch_end
    logger.info(
        f"Batch: {settings.account_email_base}+{start}@gmail.com ~ +{end}@gmail.com"
    )

    accounts = run_batch()

    # Report
    print("\n\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    print(f"  Accounts: {len(accounts)}\n")
    for a in accounts:
        print(f"  [{a['email']}]  pwd: {a['password']}")
        for k in a.get("api_keys", []):
            print(f"    {k['group_name']:20s}  {k['key_value']}")
        print()

    # Save
    out = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "config": {
            "base_url": settings.aether_base_url,
            "email_base": settings.account_email_base,
            "range": f"+{start}~+{end}",
        },
        "accounts": accounts,
    }
    with open("aether_accounts.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    logger.info("Saved to aether_accounts.json")


if __name__ == "__main__":
    main()
