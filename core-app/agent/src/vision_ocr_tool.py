from __future__ import annotations

import boto3
from google.cloud import vision

from .config import aws_region
from .google_secret import VISION_SCOPES, get_google_secret, service_account_credentials


def extract_text(bucket: str, key: str) -> str:
    region = aws_region()
    s3 = boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
    )
    image_bytes = s3.get_object(Bucket=bucket, Key=key)["Body"].read()

    credentials = service_account_credentials(get_google_secret(), VISION_SCOPES)
    client = vision.ImageAnnotatorClient(credentials=credentials)
    response = client.document_text_detection(image=vision.Image(content=image_bytes))

    if response.error.message:
        raise RuntimeError(f"Cloud Vision OCR failed: {response.error.message}")

    if response.full_text_annotation and response.full_text_annotation.text:
        return response.full_text_annotation.text

    texts = response.text_annotations or []
    if texts:
        return texts[0].description

    return ""
