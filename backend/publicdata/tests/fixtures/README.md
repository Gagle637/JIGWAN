# 실거래 API 녹화 응답

여기에 실제 국토부 실거래가 API(data.go.kr) 응답을 그대로 저장하면, 그 응답을 재생해 전체
파이프라인(수집→정규화→매칭→저장)을 검증하는 통합 테스트를 켤 수 있다.

## 넣는 방법

서비스명을 파일명으로 쓴다(예: `RTMSDataSvcAptTradeDev.xml`, `RTMSDataSvcAptRent.xml`, ...).
개인정보(실제 주소·거래금액)가 민감하다고 판단되면 값을 적당히 바꿔도 되지만, **태그 구조와
대소문자는 실제 응답 그대로** 유지해야 한다(태그 대소문자가 문서마다 다르다는 점 자체가
`molit_client.py`가 검증해야 할 대상이다).

## 지금 상태

이 디렉터리가 비어 있으면(README만 있으면) 통합 테스트는 자동으로 스킵된다. 지금까지 만든
단위 테스트(`test_trade_fields.py`, `test_pnu.py`, `test_matching.py`, `test_molit_client.py`,
`test_sync.py`)는 spec.md 8-7 표에 적힌 필드명을 기준으로 한 최소 예시로 만들었고, 실제 전체
응답으로 검증된 것은 아니다.
