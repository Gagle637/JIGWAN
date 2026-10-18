"""CDSE S3(eodata)에서 필요한 밴드 파일 6개 + MTD_MSIL2A.xml만 받는다(결정 사항 2·3·4).

SAFE 전체를 받지 않는다. https 서명 URL은 쓰지 않고 s3:// 경로를 S3 키로 그대로 읽는다.
"""
from pathlib import Path
from urllib.parse import urlparse

import boto3
import botocore.exceptions as botocore_exceptions
from django.conf import settings

from core.exceptions import ExternalCallError

# 정확히 지정된 asset 키만 쓴다(패턴 매칭 금지) — 같은 밴드가 해상도별로 여러 키로 존재한다.
ASSET_KEYS = ["B02_10m", "B03_10m", "B04_10m", "B08_10m", "B11_20m", "SCL_20m"]

_RETRYABLE_ERROR_CODES = {"InternalError", "SlowDown", "ServiceUnavailable", "RequestTimeout"}


def parse_s3_uri(href: str) -> tuple[str, str]:
    """'s3://eodata/Sentinel-2/...' -> ('eodata', 'Sentinel-2/...')."""
    parsed = urlparse(href)
    if parsed.scheme != "s3":
        raise ValueError(f"s3:// 경로가 아닙니다: {href}")
    return parsed.netloc, parsed.path.lstrip("/")


def mtd_href_for(band_href: str) -> str:
    """band href를 '.SAFE/'까지 자르고 MTD_MSIL2A.xml을 붙인다(결정 사항 2, 별도 asset 키 없음)."""
    marker = ".SAFE/"
    idx = band_href.find(marker)
    if idx == -1:
        raise ValueError(f".SAFE 경로를 찾을 수 없습니다: {band_href}")
    return band_href[: idx + len(marker)] + "MTD_MSIL2A.xml"


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.CDSE_S3_ENDPOINT,
        region_name="default",
        aws_access_key_id=settings.CDSE_S3_ACCESS_KEY,
        aws_secret_access_key=settings.CDSE_S3_SECRET_KEY,
    )


def _download(client, bucket: str, key: str, local_path: Path, context: str) -> None:
    try:
        client.download_file(bucket, key, str(local_path))
    except botocore_exceptions.ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in _RETRYABLE_ERROR_CODES:
            raise ExternalCallError(f"{context}: {error_code}") from exc
        raise  # NoSuchKey·AccessDenied 등은 데이터/권한 문제 -> 재시도 없이 즉시 failed
    except (
        botocore_exceptions.EndpointConnectionError,
        botocore_exceptions.ConnectTimeoutError,
        botocore_exceptions.ReadTimeoutError,
    ) as exc:
        raise ExternalCallError(f"{context}: {exc}") from exc


def download_scene_files(item, dest_dir: Path) -> dict[str, Path]:
    """ASSET_KEYS 6개 + MTD_MSIL2A.xml을 dest_dir에 받아 {키: 로컬경로} dict를 돌려준다."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    client = get_s3_client()

    paths: dict[str, Path] = {}
    mtd_href = None
    for asset_key in ASSET_KEYS:
        asset = item.assets.get(asset_key)
        if asset is None:
            raise ValueError(f"{item.id}에 asset '{asset_key}'가 없습니다.")
        bucket, key = parse_s3_uri(asset.href)
        local_path = dest_dir / Path(key).name
        _download(client, bucket, key, local_path, context=f"{item.id} {asset_key}")
        paths[asset_key] = local_path
        if mtd_href is None:
            mtd_href = mtd_href_for(asset.href)

    mtd_bucket, mtd_key = parse_s3_uri(mtd_href)
    mtd_path = dest_dir / "MTD_MSIL2A.xml"
    _download(client, mtd_bucket, mtd_key, mtd_path, context=f"{item.id} MTD_MSIL2A.xml")
    paths["MTD"] = mtd_path

    return paths
