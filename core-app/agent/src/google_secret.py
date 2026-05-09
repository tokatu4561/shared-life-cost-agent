from __future__ import annotations

import json

import boto3
from google.oauth2 import service_account

from .config import MissingConfigurationError, aws_region, required_env

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
VISION_SCOPES = ["https://www.googleapis.com/auth/cloud-vision"]


def get_google_secret() -> dict:
    region = aws_region()
    secret_arn = required_env("GOOGLE_SECRET_ARN")
    secretsmanager = boto3.client(
        "secretsmanager",
        region_name=region,
        endpoint_url=f"https://secretsmanager.{region}.amazonaws.com",
    )
    secret_value = secretsmanager.get_secret_value(SecretId=secret_arn)
    secret_string = secret_value.get("SecretString")
    if secret_string is None:
        raise MissingConfigurationError(f"SecretString がありません: {secret_arn}")
    parsed = json.loads(secret_string)
    if not isinstance(parsed, dict):
        raise MissingConfigurationError("Google Secret はJSON objectである必要があります。")
    return parsed


def spreadsheet_id(google_secret: dict) -> str:
    value = str(google_secret.get("spreadsheetId") or "").strip()
    if not value:
        raise MissingConfigurationError("Google Secret の spreadsheetId が未設定です。")
    return value


def service_account_credentials(google_secret: dict, scopes: list[str]):
    credentials_info = google_secret.get("serviceAccount")
    if credentials_info is None:
        credentials_info = google_secret.get("serviceAccountJson")
    if isinstance(credentials_info, str):
        credentials_info = json.loads(credentials_info)
    if not isinstance(credentials_info, dict):
        raise MissingConfigurationError("Google Secret の serviceAccount が未設定です。")
    return service_account.Credentials.from_service_account_info(credentials_info, scopes=scopes)
