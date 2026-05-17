import poplib
import email
import re
import time
import logging
from email.header import decode_header
from typing import Optional

logger = logging.getLogger(__name__)


class GmailPop3Client:
    def __init__(
        self,
        email_address: str,
        app_password: str,
        host: str = "pop.gmail.com",
        port: int = 995,
    ):
        self.email_address = email_address
        self.app_password = app_password
        self.host = host
        self.port = port
        self._conn: Optional[poplib.POP3_SSL] = None

    def connect(self):
        self._conn = poplib.POP3_SSL(self.host, self.port)
        self._conn.user(self.email_address)
        self._conn.pass_(self.app_password)
        logger.info("Connected to Gmail POP3")

    def disconnect(self):
        if self._conn:
            try:
                self._conn.quit()
            except Exception:
                pass
            self._conn = None

    def _decode_subject(self, raw: bytes) -> str:
        decoded_parts = decode_header(raw)
        parts = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                parts.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                parts.append(part)
        return "".join(parts)

    def _get_email_body(self, msg: email.message.Message) -> str:
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body += payload.decode("utf-8", errors="replace")
                    except Exception:
                        pass
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="replace")
            except Exception:
                pass
        return body

    def wait_for_verification_code(
        self, expected_email: str, timeout: int = 120, interval: int = 5
    ) -> Optional[str]:
        """
        Wait for a verification code email to arrive.
        Returns the 6-digit code or None on timeout.
        """
        start = time.time()
        code_pattern = re.compile(r"(\d{6})")

        while time.time() - start < timeout:
            try:
                if not self._conn:
                    self.connect()

                msg_count = len(self._conn.list()[1])
                logger.debug(f"POP3 inbox has {msg_count} messages")

                for i in range(msg_count, 0, -1):
                    raw = self._conn.retr(i)
                    raw_msg = b"\n".join(raw[1])
                    msg = email.message_from_bytes(raw_msg)

                    to_addr = msg.get("To", "")
                    subject = self._decode_subject(msg.get("Subject", ""))
                    body = self._get_email_body(msg)

                    if expected_email.lower() in to_addr.lower():
                        # Search for verification code
                        all_text = f"{subject}\n{body}"
                        match = code_pattern.search(all_text)
                        if match:
                            code = match.group(1)
                            logger.info(
                                f"Found verification code {code} for {expected_email}"
                            )
                            return code

                logger.debug(f"No code found yet, retrying in {interval}s...")
            except Exception as e:
                logger.warning(f"POP3 error: {e}, reconnecting...")
                try:
                    self.disconnect()
                    self.connect()
                except Exception:
                    pass

            time.sleep(interval)

        logger.warning(f"Timeout waiting for verification code for {expected_email}")
        return None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
