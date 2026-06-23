"""Google Sheets istemcisi. Gmail OAuth credentials kullanarak Sheets ve Gmail API'ye erişir."""
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",
]


def _get_credentials() -> Credentials:
    return Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        scopes=SCOPES,
    )


def get_sheets_service():
    return build("sheets", "v4", credentials=_get_credentials())


def get_gmail_service():
    return build("gmail", "v1", credentials=_get_credentials())


def append_to_sheet(spreadsheet_id: str, range_name: str, values: list):
    """Sheets'in sonuna yeni satırlar ekler."""
    service = get_sheets_service()
    body = {"values": values}
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()


def clear_and_write_sheet(spreadsheet_id: str, range_name: str, values: list):
    """Sheets aralığını temizler ve baştan yazar."""
    service = get_sheets_service()
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id, range=range_name
    ).execute()
    if values:
        body = {"values": values}
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()
