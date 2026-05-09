from __future__ import annotations

import os
import re


class MissingConfigurationError(RuntimeError):
    pass


class SheetsError(RuntimeError):
    pass


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None:
        raise MissingConfigurationError(f"環境変数 {name} が未設定です。")
    return value


def aws_region() -> str:
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "ap-northeast-1"
    region = region.strip()
    if not re.fullmatch(r"[a-z]{2}-[a-z]+-\d", region):
        return "ap-northeast-1"
    return region
