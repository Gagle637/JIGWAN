import pytest

from publicdata.models import Trade
from publicdata.sync import (
    current_and_previous_month,
    months_back,
    persist_batch,
    sync_trades_for_months,
)


def _row(**overrides):
    base = dict(
        house_type=Trade.HouseType.OFFICETEL,
        deal_type=Trade.DealType.SALE,
        sgg_code="30110",
        bjd_name="효동",
        jibun_raw="153-3",
        apt_seq=None,
        building_name="테스트빌딩",
        area_m2=50.0,
        price=10000,
        deposit=None,
        monthly_rent=None,
        deal_ym="2026-09",
        deal_day=1,
        is_canceled=False,
        canceled_at=None,
        floor=3,
        build_year=2010,
        pnu_hint=None,
    )
    base.update(overrides)
    return base


@pytest.mark.django_db
def test_persist_batch_computes_match_rate_and_failures():
    rows = [
        _row(jibun_raw="153-3"),  # region 미적재 -> region_not_found
        _row(jibun_raw="2024-01-05"),  # 날짜로 둔갑한 지번 -> jibun_parse_failed
        _row(house_type=Trade.HouseType.DETACHED, jibun_raw=None),  # 매칭 대상 아님
    ]
    summary = persist_batch(rows)

    assert summary[Trade.HouseType.OFFICETEL]["total"] == 2
    assert summary[Trade.HouseType.OFFICETEL]["matched"] == 0
    assert summary[Trade.HouseType.OFFICETEL]["failed"] == {
        "region_not_found": 1,
        "jibun_parse_failed": 1,
    }
    assert summary[Trade.HouseType.DETACHED]["matched"] is None
    assert summary[Trade.HouseType.DETACHED]["match_rate_pct"] is None
    assert Trade.objects.count() == 3


@pytest.mark.django_db
def test_persist_batch_replaces_same_group_idempotently():
    rows = [_row(jibun_raw="153-3")]
    persist_batch(rows)
    assert (
        Trade.objects.filter(house_type=Trade.HouseType.OFFICETEL, deal_ym="2026-09").count() == 1
    )

    persist_batch(rows)  # 재실행 — 같은 (house_type,deal_type,sgg_code,deal_ym)은 교체되어야 함
    assert (
        Trade.objects.filter(house_type=Trade.HouseType.OFFICETEL, deal_ym="2026-09").count() == 1
    )


@pytest.mark.django_db
def test_persist_batch_skips_rows_without_deal_ym():
    rows = [_row(deal_ym=None)]
    summary = persist_batch(rows)
    assert summary == {}
    assert Trade.objects.count() == 0


def test_sync_trades_for_months_requires_api_key(settings):
    settings.DATA_GO_KR_API_KEY = ""
    with pytest.raises(ValueError):
        sync_trades_for_months(["202609"])


@pytest.mark.django_db
def test_sync_trades_for_months_collects_and_persists(monkeypatch, settings):
    settings.DATA_GO_KR_API_KEY = "fake-key"

    async def fake_collect_month(sgg_codes, deal_ymd, service_key):
        return [_row(deal_ym="2026-09")]

    monkeypatch.setattr("publicdata.sync.collect_month", fake_collect_month)

    overall = sync_trades_for_months(["202609"])

    assert "202609" in overall
    assert Trade.objects.filter(deal_ym="2026-09").count() == 1


def test_current_and_previous_month_format():
    months = current_and_previous_month()
    assert len(months) == 2
    assert all(len(m) == 6 and m.isdigit() for m in months)


def test_months_back_count_and_order():
    months = months_back(3)
    assert len(months) == 3
    assert months == sorted(months, reverse=True)
