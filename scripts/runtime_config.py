import argparse
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

DEFAULT_LOCAL_API_URL = "http://127.0.0.1:8000/api/v1"
DEFAULT_BUSINESS_DB_PATH = "./nt_fi_report.sqlite"


def _get_optional_cli_arg(flag: str) -> Optional[str]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(flag)
    args, _ = parser.parse_known_args()
    arg_name = flag.lstrip("-").replace("-", "_")
    return getattr(args, arg_name)


def get_api_base_url() -> str:
    cli_value = _get_optional_cli_arg("--url")
    base_url = cli_value or os.getenv("API_BASE_URL") or DEFAULT_LOCAL_API_URL
    return base_url.rstrip("/")


def get_business_db_path() -> str:
    cli_value = _get_optional_cli_arg("--db-path")
    db_path = cli_value or os.getenv("BUSINESS_DB_PATH") or DEFAULT_BUSINESS_DB_PATH
    path = Path(db_path)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return str(path.resolve())