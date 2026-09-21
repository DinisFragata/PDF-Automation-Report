import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

def load_data_from_google_sheets(json_file, sheet_name):
    creds = Credentials.from_service_account_file(
        json_file,
        scopes=["https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"]
    )

    gc = gspread.authorize(creds)
    sh = gc.open(sheet_name)
    worksheet = sh.sheet1

    # Read all the data from the sheet
    data = worksheet.get_all_records()

    # Convert to DataFrame
    df = pd.DataFrame(data)

    return df

def clean_data(df):
    df = df.dropna().copy()  # remove lines with missing values

    # Convert columns to appropriate data types; unparseable values are dropped
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    if 'Quantity' in df.columns:
        df['Quantity'] = pd.to_numeric(df['Quantity'], errors='coerce')
    if 'Price' in df.columns:
        df['Price'] = pd.to_numeric(df['Price'], errors='coerce')

    df = df.dropna()

    if 'Quantity' in df.columns:
        df = df[df['Quantity'] >= 0].copy()
        df['Quantity'] = df['Quantity'].astype(int)
    if 'Price' in df.columns:
        df = df[df['Price'] >= 0].copy()
        df['Price'] = df['Price'].astype(float)

    return df
