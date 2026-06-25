"""
Send daily report via SMTP SSL with HTML body, embedded images, and attachments.
3 retries with exponential backoff.
"""
import argparse
import logging
import os
import smtplib
import time
from datetime import date
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, formataddr
from pathlib import Path
from typing import Optional

from config import (
    EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASSWORD, EMAIL_TO,
    SENDGRID_API_KEY, SENDGRID_FROM_EMAIL, MAX_EMAIL_ATTACHMENT_MB, OUTPUT_DIR,
)

logger = logging.getLogger("email")

MAX_RETRIES = 3
RETRY_DELAYS = [5, 30, 120]  # seconds


def is_github_actions() -> bool:
    return os.getenv("GITHUB_ACTIONS") == "true"


def validate_sendgrid_config() -> bool:
    """Validate SendGrid settings without printing secret values."""
    checks = {
        "SENDGRID_API_KEY": bool(SENDGRID_API_KEY),
        "SENDGRID_FROM_EMAIL": bool(SENDGRID_FROM_EMAIL),
        "EMAIL_TO": bool(EMAIL_TO),
    }
    for name, configured in checks.items():
        logger.info("%s: %s", name, "configured" if configured else "not configured")
    return all(checks.values())


def send_email_sendgrid(html_content: str, md_content: str = "",
                         date_str: Optional[str] = None,
                         attachments: Optional[list[Path]] = None) -> bool:
    """Send email via SendGrid API v3. Returns True on success."""
    import base64
    import httpx

    today = date.today()
    ds = date_str or today.strftime("%Y%m%d")
    subject = f"AI 前沿与计算机科学论文日报 \u2014 {ds}"

    # Build SendGrid payload
    payload = {
        "personalizations": [{"to": [{"email": EMAIL_TO}]}],
        "from": {"email": SENDGRID_FROM_EMAIL, "name": "AI \u524d\u6cbf\u65e5\u62a5"},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": (md_content or "")[:5000]},
            {"type": "text/html", "value": html_content},
        ],
    }

    # Attachments
    if attachments:
        payload["attachments"] = []
        total_mb = 0
        for fpath in attachments:
            fpath = Path(fpath)
            if not fpath.exists():
                continue
            fsize_mb = fpath.stat().st_size / (1024 * 1024)
            if total_mb + fsize_mb > MAX_EMAIL_ATTACHMENT_MB:
                logger.warning("Attachment budget exceeded, skipping %s", fpath.name)
                continue
            with open(fpath, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            payload["attachments"].append({
                "filename": fpath.name,
                "content": b64,
            })
            total_mb += fsize_mb
            logger.debug("Attached: %s (%.1f MB)", fpath.name, fsize_mb)

    # Try up to 2 times
    for attempt in range(2):
        try:
            resp = httpx.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers={
                    "Authorization": f"Bearer {SENDGRID_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            if resp.status_code in (200, 201, 202):
                logger.info("Email sent via SendGrid!")
                sent_file = OUTPUT_DIR / f"daily_sent_{ds}.ok"
                sent_file.write_text(f"Sent via SendGrid at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                return True
            else:
                logger.warning("SendGrid attempt %d failed: HTTP %s - %s",
                               attempt + 1, resp.status_code, resp.text[:200])
        except Exception as exc:
            logger.warning("SendGrid attempt %d failed: %s", attempt + 1, exc)

        if attempt == 0:
            time.sleep(3)

    logger.error("All SendGrid attempts failed.")
    return False


def send_email_smtp(html_content: str, md_content: str = "",
                    date_str: Optional[str] = None,
                    attachments: Optional[list[Path]] = None) -> bool:
    """Send daily report email via SMTP. Intended for local testing."""
    today = date.today()
    ds = date_str or today.strftime("%Y%m%d")

    if not all([EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASSWORD, EMAIL_TO]):
        logger.error("SMTP config incomplete. Check .env")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr(("AI \u524d\u6cbf\u65e5\u62a5", EMAIL_USER))
    msg["To"] = EMAIL_TO
    msg["Subject"] = f"AI \u524d\u6cbf\u4e0e\u8ba1\u7b97\u673a\u79d1\u5b66\u8bba\u6587\u65e5\u62a5 \u2014 {ds}"
    msg["Date"] = formatdate(localtime=True)

    # Plain text fallback
    if md_content:
        msg.attach(MIMEText(md_content[:5000], "plain", "utf-8"))
    # HTML body
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    # Attachments (Excel, PDFs, etc.)
    total_attached_mb = 0
    if attachments:
        mixed = MIMEMultipart("mixed")
        mixed.attach(msg)
        msg = mixed

        for fpath in attachments:
            fpath = Path(fpath)
            if not fpath.exists():
                logger.debug("Attachment not found: %s", fpath)
                continue
            fsize_mb = fpath.stat().st_size / (1024 * 1024)
            if total_attached_mb + fsize_mb > MAX_EMAIL_ATTACHMENT_MB:
                logger.warning("Attachment size budget exceeded, skipping %s", fpath.name)
                continue
            try:
                with open(fpath, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                import email.encoders
                email.encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename=\"{fpath.name}\""
                )
                msg.attach(part)
                total_attached_mb += fsize_mb
                logger.debug("Attached: %s (%.1f MB)", fpath.name, fsize_mb)
            except Exception as exc:
                logger.warning("Failed to attach %s: %s", fpath.name, exc)

    # Send with retries
    last_error = ""
    for attempt in range(MAX_RETRIES):
        try:
            logger.info("Email attempt %d/%d to %s via %s:%d",
                        attempt + 1, MAX_RETRIES, EMAIL_TO, EMAIL_HOST, EMAIL_PORT)
            if EMAIL_PORT == 465:
                with smtplib.SMTP_SSL(host=EMAIL_HOST, port=EMAIL_PORT, timeout=30) as server:
                    server.login(EMAIL_USER, EMAIL_PASSWORD)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(host=EMAIL_HOST, port=EMAIL_PORT, timeout=30) as server:
                    server.starttls()
                    server.login(EMAIL_USER, EMAIL_PASSWORD)
                    server.send_message(msg)
            logger.info("Email sent successfully!")
            sent_file = OUTPUT_DIR / f"daily_sent_{ds}.ok"
            sent_file.write_text(f"Sent at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            return True
        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP authentication failed \u2014 check EMAIL_USER/EMAIL_PASSWORD")
            return False
        except smtplib.SMTPServerDisconnected as exc:
            last_error = f"SMTPServerDisconnected: {exc}"
            logger.warning("Attempt %d failed (server disconnected): %s", attempt + 1, exc)
        except smtplib.SMTPException as exc:
            last_error = f"SMTPException: {exc}"
            logger.warning("Attempt %d failed: %s", attempt + 1, exc)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Attempt %d failed: %s", attempt + 1, exc)

        if attempt < MAX_RETRIES - 1:
            delay = RETRY_DELAYS[attempt] if attempt < len(RETRY_DELAYS) else 60
            logger.info("Waiting %d seconds before retry\u2026", delay)
            time.sleep(delay)

    logger.error("All %d email attempts failed. Last error: %s", MAX_RETRIES, last_error)
    return False


def send_email(html_content: str, md_content: str = "",
               date_str: Optional[str] = None,
               attachments: Optional[list[Path]] = None,
               provider: str = "auto") -> bool:
    """Send daily report email using the selected provider."""
    if provider not in {"auto", "sendgrid", "smtp"}:
        logger.error("Unknown email provider: %s", provider)
        return False

    effective_provider = "sendgrid" if provider == "auto" and is_github_actions() else provider

    if effective_provider == "sendgrid":
        if not validate_sendgrid_config():
            logger.error("SendGrid config incomplete; email not sent.")
            return False
        logger.info("Using SendGrid to send email.")
        return send_email_sendgrid(html_content, md_content, date_str, attachments)

    if effective_provider == "smtp":
        logger.info("Using SMTP to send email.")
        return send_email_smtp(html_content, md_content, date_str, attachments)

    if validate_sendgrid_config():
        logger.info("Using SendGrid to send email.")
        if send_email_sendgrid(html_content, md_content, date_str, attachments):
            return True
        logger.warning("SendGrid failed locally, falling back to SMTP.")
    else:
        logger.info("SendGrid config incomplete locally; falling back to SMTP.")

    return send_email_smtp(html_content, md_content, date_str, attachments)


def send_test_email(provider: str = "auto") -> bool:
    """Send a simple test email to verify provider configuration."""
    html = """<html><body>
    <h2>邮件测试</h2>
    <p>这是一封来自 AI 前沿日报系统的测试邮件。</p>
    <p>如果你收到这封邮件，说明当前发信通道配置正确。</p>
    <p>发送时间：{time}</p>
    </body></html>""".format(time=time.strftime("%Y-%m-%d %H:%M:%S"))
    return send_email(html, md_content="邮件测试", provider=provider)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Send daily AI paper report email")
    parser.add_argument("--provider", choices=["auto", "sendgrid", "smtp"], default="auto",
                        help="Email provider to use")
    parser.add_argument("--test", action="store_true", help="Send a test email")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    if args.test:
        logger.info("Sending test email…")
        success = send_test_email(provider=args.provider)
        print(f"Test email {'sent successfully!' if success else 'FAILED'}")
        return 0 if success else 1

    # Try to find today's report
    today = date.today().strftime("%Y%m%d")
    md_path = OUTPUT_DIR / f"daily_combined_report_{today}.md"
    html_path = OUTPUT_DIR / f"daily_combined_report_{today}.html"

    if not html_path.exists():
        logger.error("No report found for today: %s", html_path)
        return 1

    md_content = md_path.read_text("utf-8") if md_path.exists() else ""
    html_content = html_path.read_text("utf-8")

    # Collect attachments (Excel files, PDFs)
    attachments = sorted(OUTPUT_DIR.glob(f"daily_aihot_{today}.xlsx"))
    attachments += sorted(OUTPUT_DIR.glob(f"daily_cs_papers_{today}.xlsx"))

    success = send_email(html_content, md_content, date_str=today,
                         attachments=attachments, provider=args.provider)
    print(f"Email {'sent successfully!' if success else 'FAILED'}")
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
