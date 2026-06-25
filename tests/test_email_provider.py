"""Email provider selection tests."""
import smtplib

import send_daily_report_email as mailer


def test_github_actions_sendgrid_failure_does_not_fallback_to_smtp(monkeypatch):
    smtp_called = False

    def fail_if_smtp_used(*args, **kwargs):
        nonlocal smtp_called
        smtp_called = True
        raise smtplib.SMTPException("smtp should not be used in GitHub Actions")

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(mailer, "SENDGRID_API_KEY", "configured")
    monkeypatch.setattr(mailer, "SENDGRID_FROM_EMAIL", "sender@example.com")
    monkeypatch.setattr(mailer, "EMAIL_TO", "receiver@example.com")
    monkeypatch.setattr(mailer, "EMAIL_HOST", "smtp.qq.com")
    monkeypatch.setattr(mailer, "EMAIL_PORT", 465)
    monkeypatch.setattr(mailer, "EMAIL_USER", "sender@example.com")
    monkeypatch.setattr(mailer, "EMAIL_PASSWORD", "configured")
    monkeypatch.setattr(mailer, "send_email_sendgrid", lambda *args, **kwargs: False)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", fail_if_smtp_used)
    monkeypatch.setattr(mailer.smtplib, "SMTP", fail_if_smtp_used)

    assert mailer.send_email("<p>report</p>") is False
    assert smtp_called is False


def test_sendgrid_provider_requires_sendgrid_config(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(mailer, "SENDGRID_API_KEY", "")
    monkeypatch.setattr(mailer, "SENDGRID_FROM_EMAIL", "")
    monkeypatch.setattr(mailer, "EMAIL_TO", "receiver@example.com")

    assert mailer.send_email("<p>report</p>", provider="sendgrid") is False


def test_sendgrid_test_command_uses_sendgrid_provider(monkeypatch):
    seen = {}

    def fake_send_test_email(provider="auto"):
        seen["provider"] = provider
        return True

    monkeypatch.setattr(mailer, "send_test_email", fake_send_test_email)

    assert mailer.main(["--provider", "sendgrid", "--test"]) == 0
    assert seen["provider"] == "sendgrid"
