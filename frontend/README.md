# 지관 프론트엔드

Vite + React + TypeScript + Tailwind CSS.

## 실행

```bash
npm install
npm run dev
```

백엔드(`backend/`)가 `http://localhost:8000`에서 떠 있어야 한다.

## 환경 변수

`.env.example` 참고.

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `VITE_API_BASE` | `http://localhost:8000` | 백엔드 API 주소 |

## 좌표계

- API 입출력: EPSG:4326
- 지도 표출: EPSG:3857
