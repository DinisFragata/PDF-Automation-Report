import os
import uuid
import pandas as pd

from data_processing import clean_data, load_data_from_google_sheets
from report import generate_charts
from pdf_generator import generate_pdf


REQUIRED_COLUMNS = ["Date", "Product", "Quantity", "Price", "Seller"]


def validate_sales_dataframe(df: pd.DataFrame) -> pd.DataFrame:

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {', '.join(missing_columns)}"
        )

    df = df[REQUIRED_COLUMNS]
    df = clean_data(df)

    if df.empty:
        raise ValueError("The uploaded file has no valid rows after cleaning.")

    return df


def generate_sales_report_from_dataframe(
    df: pd.DataFrame,
    output_file: str | None = None,
    title: str = "Sales Report",
    header_text: str = "PDF Automation Report",
) -> str:

    os.makedirs("assets", exist_ok=True)

    if output_file is None:
        file_id = str(uuid.uuid4())
        output_file = os.path.join("assets", f"sales_report_{file_id}.pdf")

    df = validate_sales_dataframe(df)

    generate_charts(df)

    generate_pdf(
        df,
        output_file=output_file,
        pdf_settings={
            "title": title,
            "header_text": header_text,
        },
    )

    return output_file


def generate_sales_report_from_excel(
    excel_path: str,
    output_file: str | None = None,
    title: str = "Sales Report",
    header_text: str = "PDF Automation Report",
) -> str:

    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel file not found: {excel_path}")

    df = pd.read_excel(excel_path)

    return generate_sales_report_from_dataframe(
        df=df,
        output_file=output_file,
        title=title,
        header_text=header_text,
    )


def generate_sales_report_from_google_sheets(
    service_account_file: str,
    sheet_name: str,
    output_file: str | None = None,
    title: str = "Sales Report",
    header_text: str = "PDF Automation Report",
) -> str:

    df = load_data_from_google_sheets(
        json_file=service_account_file,
        sheet_name=sheet_name,
    )

    return generate_sales_report_from_dataframe(
        df=df,
        output_file=output_file,
        title=title,
        header_text=header_text,
    )