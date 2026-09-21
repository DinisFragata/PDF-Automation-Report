import mimetypes
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable, List, Optional, Union

from dotenv import load_dotenv

load_dotenv()


RecipientInput = Union[str, Iterable[str]]


def _split_recipients(recipients: RecipientInput) -> List[str]:
    if isinstance(recipients, str):
        raw_recipients = recipients.split(",")
    else:
        raw_recipients = list(recipients)

    cleaned_recipients = [
        email.strip()
        for email in raw_recipients
        if email and email.strip()
    ]

    if not cleaned_recipients:
        raise ValueError("Please provide at least one recipient email.")

    return cleaned_recipients


def _get_smtp_config() -> dict:
    smtp_host = os.getenv("SMTP_HOST", "smtppro.zoho.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_security = os.getenv("SMTP_SECURITY", "ssl").lower()

    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")

    smtp_from_email = os.getenv("SMTP_FROM_EMAIL", smtp_username)
    smtp_from_name = os.getenv("SMTP_FROM_NAME", "Automated Sales Report")

    if not smtp_username:
        raise RuntimeError("Missing SMTP_USERNAME environment variable.")

    if not smtp_password:
        raise RuntimeError("Missing SMTP_PASSWORD environment variable.")

    if not smtp_from_email:
        raise RuntimeError("Missing SMTP_FROM_EMAIL environment variable.")

    if smtp_security not in ["ssl", "tls"]:
        raise RuntimeError("SMTP_SECURITY must be either 'ssl' or 'tls'.")

    return {
        "host": smtp_host,
        "port": smtp_port,
        "security": smtp_security,
        "username": smtp_username,
        "password": smtp_password,
        "from_email": smtp_from_email,
        "from_name": smtp_from_name,
    }


def send_email_zoho(
    recipients: RecipientInput,
    subject: str,
    body: str,
    attachment_path: Optional[str] = None,
    attachment_name: Optional[str] = None,
    max_recipients: int = 1,
) -> dict:
    smtp_config = _get_smtp_config()
    recipient_list = _split_recipients(recipients)

    if len(recipient_list) > max_recipients:
        raise ValueError(f"At most {max_recipients} recipient(s) are allowed.")

    email_subject = subject.strip() or "Automated Sales Report"

    email_body = body.strip() or (
        "Hello,\n\n"
        "Attached is your automated sales report.\n\n"
        "Best regards,\n"
        "Automated Sales Report System"
    )

    message = EmailMessage()
    message["To"] = ", ".join(recipient_list)
    message["From"] = f"{smtp_config['from_name']} <{smtp_config['from_email']}>"
    message["Subject"] = email_subject
    message.set_content(email_body)

    if attachment_path:
        path = Path(attachment_path)

        if not path.exists():
            raise FileNotFoundError(f"Attachment not found: {attachment_path}")

        content_type, _ = mimetypes.guess_type(path.name)

        if content_type:
            maintype, subtype = content_type.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"

        with path.open("rb") as file:
            message.add_attachment(
                file.read(),
                maintype=maintype,
                subtype=subtype,
                filename=attachment_name or path.name,
            )

    if smtp_config["security"] == "ssl":
        with smtplib.SMTP_SSL(
            smtp_config["host"],
            smtp_config["port"],
            timeout=30,
        ) as smtp:
            smtp.login(
                smtp_config["username"],
                smtp_config["password"],
            )
            smtp.send_message(message)

    else:
        with smtplib.SMTP(
            smtp_config["host"],
            smtp_config["port"],
            timeout=30,
        ) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(
                smtp_config["username"],
                smtp_config["password"],
            )
            smtp.send_message(message)

    return {
        "sent": True,
        "provider": "zoho",
        "recipients": recipient_list,
        "subject": email_subject,
    }