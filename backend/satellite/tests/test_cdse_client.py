"""CDSE S3 클라이언트: URL 조립, 재시도할 오류·안 할 오류 분기를 boto3를 목으로 검증한다
(spec 9-5: "외부 API는 녹화한 응답으로 목 처리")."""
from unittest.mock import MagicMock

import botocore.exceptions as botocore_exceptions
import pytest

from core.exceptions import ExternalCallError
from satellite import cdse_client

ASSET_BASE = (
    "s3://eodata/Sentinel-2/MSI/L2A/2026/08/09/"
    "S2B_MSIL2A_20260809T085559_N0512_R007_T52SCF_20260809T111845.SAFE"
    "/GRANULE/L2A_T52SCF_A000000_20260809T090000/IMG_DATA/R10m"
)


class FakeAsset:
    def __init__(self, href):
        self.href = href


class FakeItem:
    def __init__(self, item_id, assets):
        self.id = item_id
        self.assets = assets


def _make_item():
    assets = {key: FakeAsset(f"{ASSET_BASE}/{key}.jp2") for key in cdse_client.ASSET_KEYS}
    return FakeItem("S2B_MSIL2A_20260809T085559_N0512_R007_T52SCF_20260809T111845", assets)


def test_parse_s3_uri_splits_bucket_and_key():
    bucket, key = cdse_client.parse_s3_uri("s3://eodata/Sentinel-2/x/y.jp2")

    assert bucket == "eodata"
    assert key == "Sentinel-2/x/y.jp2"


def test_parse_s3_uri_rejects_non_s3_scheme():
    with pytest.raises(ValueError):
        cdse_client.parse_s3_uri("https://example.com/x")


def test_mtd_href_for_truncates_at_safe_and_appends_mtd_filename():
    href = f"{ASSET_BASE}/B02_10m.jp2"

    assert cdse_client.mtd_href_for(href) == (
        "s3://eodata/Sentinel-2/MSI/L2A/2026/08/09/"
        "S2B_MSIL2A_20260809T085559_N0512_R007_T52SCF_20260809T111845.SAFE/MTD_MSIL2A.xml"
    )


def test_mtd_href_for_raises_when_no_safe_marker():
    with pytest.raises(ValueError):
        cdse_client.mtd_href_for("s3://eodata/no-safe-here/file.jp2")


def test_download_scene_files_requests_every_asset_key_plus_mtd(tmp_path, monkeypatch):
    item = _make_item()
    fake_client = MagicMock()
    monkeypatch.setattr(cdse_client, "get_s3_client", lambda: fake_client)

    paths = cdse_client.download_scene_files(item, tmp_path)

    assert set(paths.keys()) == set(cdse_client.ASSET_KEYS) | {"MTD"}
    assert fake_client.download_file.call_count == len(cdse_client.ASSET_KEYS) + 1
    for call in fake_client.download_file.call_args_list:
        bucket = call.args[0]
        assert bucket == "eodata"


def test_download_scene_files_missing_asset_raises_value_error(tmp_path, monkeypatch):
    item = FakeItem("no-assets", {})
    monkeypatch.setattr(cdse_client, "get_s3_client", lambda: MagicMock())

    with pytest.raises(ValueError):
        cdse_client.download_scene_files(item, tmp_path)


@pytest.mark.parametrize("error_code", ["InternalError", "SlowDown", "ServiceUnavailable", "RequestTimeout"])
def test_retryable_client_errors_become_external_call_error(tmp_path, monkeypatch, error_code):
    item = _make_item()
    fake_client = MagicMock()
    fake_client.download_file.side_effect = botocore_exceptions.ClientError(
        {"Error": {"Code": error_code}}, "GetObject"
    )
    monkeypatch.setattr(cdse_client, "get_s3_client", lambda: fake_client)

    with pytest.raises(ExternalCallError):
        cdse_client.download_scene_files(item, tmp_path)


@pytest.mark.parametrize("error_code", ["NoSuchKey", "AccessDenied"])
def test_non_retryable_client_errors_propagate_unwrapped(tmp_path, monkeypatch, error_code):
    item = _make_item()
    fake_client = MagicMock()
    fake_client.download_file.side_effect = botocore_exceptions.ClientError(
        {"Error": {"Code": error_code}}, "GetObject"
    )
    monkeypatch.setattr(cdse_client, "get_s3_client", lambda: fake_client)

    with pytest.raises(botocore_exceptions.ClientError):
        cdse_client.download_scene_files(item, tmp_path)


def test_connection_errors_become_external_call_error(tmp_path, monkeypatch):
    item = _make_item()
    fake_client = MagicMock()
    fake_client.download_file.side_effect = botocore_exceptions.EndpointConnectionError(
        endpoint_url="https://eodata.dataspace.copernicus.eu"
    )
    monkeypatch.setattr(cdse_client, "get_s3_client", lambda: fake_client)

    with pytest.raises(ExternalCallError):
        cdse_client.download_scene_files(item, tmp_path)
