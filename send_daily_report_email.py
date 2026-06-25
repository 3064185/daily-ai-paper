"""
Send daily report via SMTP SSL with HTML body, embedded images, and attachments.
3 retries with exponential backoff.
"""
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
    MAX_EMAIL_ATTACHMENT_MB, OUTPUT_DIR,
)

logger = logging.getLogger("email")

MAX_RETRIES = 3
RETRY_DELAYS = [5, 30, 120]  # seconds


def send_email(html_content: str, md_content: str = "",
               date_str: Optional[str] = None,
               attachments: Optional[list[Path]] = None) -> bool:
    """Send daily report email via SMTP SSL. Returns True on success."""
    if not all([EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASSWORD, EMAIL_TO]):
        logger.error("Email configuration incomplete. Check .env")
        return False

    today = date.today()
    ds = date_str or today.strftime("%Y%m%d")

    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr(("AI 前沿日报", EMAIL_USER))
    msg["To"] = EMAIL_TO
    msg["Subject"] = f"AI 前沿与计算机科学论文日报 — {ds}"
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
        # Copy alternative parts
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
            # Write sent marker
            sent_file = OUTPUT_DIR / f"daily_sent_{ds}.ok"
            sent_file.write_text(f"Sent at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            return True
        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP authentication failed — check EMAIL_USER/EMAIL_PASSWORD")
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
            logger.info("Waiting %d seconds before retry…", delay)
            time.sleep(delay)

    logger.error("All %d email attempts failed. Last error: %s", MAX_RETRIES, last_error)
    return False


def send_test_email() -> bool:
    """Send a simple test email to verify SMTP configuration."""
    html = """<html><body>
    <h2>SMTP 测试邮件</h2>
    <p>这是一封来自 AI 前沿日报系统的测试邮件。</p>
    <p>如果你收到这封邮件，说明 SMTP 配置正确。</p>
    <p>发送时间：{time}</p>
    </body></html>""".format(time=time.strftime("%Y-%m-%d %H:%M:%S"))
    return send_email(html, md_content="SMTP 测试邮件")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    if "--test" in sys.argv:
        logger.info("Sending test email…")
        success = send_test_email()
        print(f"Test email {'sent successfully!' if success else 'FAILED'}")
    else:
        # Try to find today's report
        today = date.today().strftime("%Y%m%d")
        md_path = OUTPUT_DIR / f"daily_combined_report_{today}.md"
        html_path = OUTPUT_DIR / f"daily_combined_report_{today}.html"

        if not html_path.exists():
            logger.error("No report found for today: %s", html_path)
            sys.exit(1)

        md_content = md_path.read_text("utf-8") if md_path.exists() else ""
        html_content = html_path.read_text("utf-8")

        # Collect attachments (Excel files, PDFs)
        attachments = sorted(OUTPUT_DIR.glob(f"daily_aihot_{today}.xlsx"))
        attachments += sorted(OUTPUT_DIR.glob(f"daily_cs_papers_{today}.xlsx"))

        success = send_email(html_content, md_content, date_str=today, attachments=attachments)
        print(f"Email {'sent successfully!' if success else 'FAILED'}")
        sys.exit(0 if success else 1)
