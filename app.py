import logging
import os
import tempfile
import time
import uuid
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from data_processing import clean_data
from email_verification import (
    RateLimitError,
    VerificationError,
    check_code_request_limits,
    check_report_email_limits,
    check_verify_attempt_limits,
    create_verification,
    is_email_enabled,
    normalize_email,
    verify_code,
)
from pdf_generator import generate_pdf
from report import generate_charts
from zoho_sender import send_email_zoho


logger = logging.getLogger("sales_report_api")

app = FastAPI(title="Automated Sales Report API")


FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "https://data-automation-reports.vercel.app",
)

allowed_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5500",
    FRONTEND_URL,
]

allowed_origins = [origin for origin in allowed_origins if origin]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


ASSETS_DIR = Path("assets")
ASSETS_DIR.mkdir(exist_ok=True)

MAX_UPLOAD_BYTES = int(float(os.getenv("MAX_UPLOAD_MB", "5")) * 1024 * 1024)
REPORT_TTL_SECONDS = 60 * 60


REQUIRED_COLUMNS = ["Date", "Product", "Quantity", "Price", "Seller"]


# Email content is fixed on the server so the public form cannot be used to
# send arbitrary text from our domain.
VERIFICATION_EMAIL_SUBJECT = "Your verification code"

VERIFICATION_EMAIL_BODY = (
    "Hello,\n\n"
    "Your verification code for the Automated Sales Report demo is: {code}\n\n"
    "It expires in 10 minutes. If you did not request it, you can ignore this email.\n\n"
    "Best regards,\n"
    "Dinis Fragata"
)

REPORT_EMAIL_SUBJECT = "Your automated sales report"

REPORT_EMAIL_BODY = (
    "Hello,\n\n"
    "Attached is your automated sales report with charts, metrics and analysis.\n\n"
    "You received this because you requested it on the Automated Sales Report demo.\n\n"
    "Best regards,\n"
    "Dinis Fragata"
)


def _error(status_code: int, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message, **extra})


def _client_ip(request: Request) -> str:
    # Behind a reverse proxy (Railway) the last X-Forwarded-For entry is the one
    # the proxy added; earlier entries can be forged by the client.
    forwarded_for = request.headers.get("x-forwarded-for", "")

    if forwarded_for:
        return forwarded_for.split(",")[-1].strip()

    return request.client.host if request.client else "unknown"


@app.get("/")
def root():
    return {
        "message": "Automated Sales Report API is running",
        "endpoints": {
            "health": "/health",
            "config": "/config",
            "request_code": "/request-code",
            "generate_report": "/generate-report",
            "download_report": "/download-report/{filename}",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def config():
    return {"email_enabled": is_email_enabled()}


def _is_excel_file(filename: str) -> bool:
    return filename.lower().endswith(".xlsx")


def _validate_dataframe_columns(df: pd.DataFrame) -> None:
    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {', '.join(missing_columns)}"
        )


def _cleanup_old_reports() -> None:
    cutoff = time.time() - REPORT_TTL_SECONDS

    for old_pdf in ASSETS_DIR.glob("sales_report_*.pdf"):
        try:
            if old_pdf.stat().st_mtime < cutoff:
                old_pdf.unlink()
        except OSError:
            pass


def _create_report_from_excel(upload_path: Path, pdf_path: Path, work_dir: Path) -> None:
    try:
        df = pd.read_excel(upload_path)
    except Exception:
        raise ValueError("Could not read the Excel file. Please upload a valid .xlsx file.") from None

    _validate_dataframe_columns(df)

    df = df[REQUIRED_COLUMNS]
    df = clean_data(df)

    if df.empty:
        raise ValueError("The uploaded file has no valid rows after cleaning.")

    # Charts go to a per-request folder so concurrent reports do not mix.
    charts_dir = work_dir / "charts"

    generate_charts(df, output_dir=str(charts_dir))

    generate_pdf(
        df,
        output_file=str(pdf_path),
        pdf_settings={
            "title": "Sales Report",
            "header_text": "Automated Sales Report",
        },
        charts_dir=str(charts_dir),
    )


@app.post("/request-code")
def request_code(request: Request, email: str = Form(...)):
    if not is_email_enabled():
        return _error(503, "Email sending is disabled on this server.")

    try:
        email = normalize_email(email)
        check_code_request_limits(email, _client_ip(request))

    except VerificationError as validation_error:
        return _error(400, str(validation_error))

    except RateLimitError as limit_error:
        return _error(429, str(limit_error))

    try:
        code, token = create_verification(email)

        send_email_zoho(
            recipients=email,
            subject=VERIFICATION_EMAIL_SUBJECT,
            body=VERIFICATION_EMAIL_BODY.format(code=code),
        )

    except Exception:
        logger.exception("Failed to send verification code")
        return _error(500, "Could not send the verification email. Please try again later.")

    return {"success": True, "token": token, "expires_in": 600}


@app.post("/generate-report")
def generate_report(
    request: Request,
    file: UploadFile = File(...),
    send_email: bool = Form(False),
    email: str = Form(""),
    code: str = Form(""),
    token: str = Form(""),
):
    if not file.filename:
        return _error(400, "Please upload a file.")

    original_filename = Path(file.filename).name

    if not _is_excel_file(original_filename):
        return _error(400, "Please upload an Excel file (.xlsx).")

    # Validate email ownership before doing any expensive work.
    if send_email:
        if not is_email_enabled():
            return _error(503, "Email sending is disabled on this server.")

        try:
            email = normalize_email(email)
            check_verify_attempt_limits(email, _client_ip(request))
            verify_code(email, code, token)
            check_report_email_limits(email)

        except VerificationError as verification_error:
            return _error(400, str(verification_error))

        except RateLimitError as limit_error:
            return _error(429, str(limit_error))

    file_content = file.file.read(MAX_UPLOAD_BYTES + 1)

    if len(file_content) > MAX_UPLOAD_BYTES:
        return _error(413, f"The file is too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")

    _cleanup_old_reports()

    file_id = str(uuid.uuid4())
    pdf_filename = f"sales_report_{file_id}.pdf"
    pdf_path = ASSETS_DIR / pdf_filename

    try:
        with tempfile.TemporaryDirectory() as work_dir_name:
            work_dir = Path(work_dir_name)
            upload_path = work_dir / "upload.xlsx"

            upload_path.write_bytes(file_content)

            _create_report_from_excel(upload_path, pdf_path, work_dir)

    except ValueError as validation_error:
        return _error(400, str(validation_error))

    except Exception:
        logger.exception("Report generation failed")
        return _error(500, "Something went wrong while generating the report.")

    download_url = f"/download-report/{pdf_filename}"

    if send_email:
        try:
            send_email_zoho(
                recipients=email,
                subject=REPORT_EMAIL_SUBJECT,
                body=REPORT_EMAIL_BODY,
                attachment_path=str(pdf_path),
                attachment_name="sales_report.pdf",
            )

        except Exception:
            logger.exception("Failed to send report email")
            return _error(
                500,
                "Report generated, but the email could not be sent.",
                download_url=download_url,
            )

    return {
        "success": True,
        "message": (
            "Report generated and sent by email successfully."
            if send_email
            else "Report generated successfully."
        ),
        "email_sent": send_email,
        "download_url": download_url,
    }


@app.get("/download-report/{filename}")
def download_report(filename: str):
    safe_name = Path(filename).name

    if not safe_name.startswith("sales_report_") or not safe_name.endswith(".pdf"):
        return _error(400, "Invalid report filename.")

    pdf_path = ASSETS_DIR / safe_name

    if not pdf_path.exists():
        return _error(404, "Report not found.")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename="sales_report.pdf",
    )
