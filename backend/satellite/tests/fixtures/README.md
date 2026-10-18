# CDSE STAC 응답 / MTD 샘플

여기에 실제 CDSE STAC item JSON과 실제 `MTD_MSIL2A.xml` 하나를 넣으면, 진짜 응답 구조(asset
키·네임스페이스·필드 값)로 전체 파이프라인을 검증하는 통합 테스트를 켤 수 있다
(`publicdata/tests/fixtures/`와 같은 방식).

## 지금 상태

이 디렉터리가 비어 있으면(README만 있으면) 통합 테스트는 자동으로 스킵된다. 지금까지 만든
단위 테스트(`test_reflectance.py`, `test_scl.py`, `test_mtd.py`, `test_stac_search.py`,
`test_seasons.py`, `test_cog.py`, `test_ingest.py`)는 spec.md 2장과 사용자가 확인해 준 asset
키·S3 경로 규칙을 기준으로 만든 최소 예시/가짜 객체로 검증한 것이고, 실제 STAC 응답이나 실제
SAFE 밴드 파일로 검증된 것은 아니다.
