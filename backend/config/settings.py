from datetime import timedelta
from pathlib import Path

import environ
from kombu import Queue

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DJANGO_DEBUG=(bool, False))
environ.Env.read_env(str(BASE_DIR.parent / ".env"))

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# 13단계: 서버가(GPU·외부 API 없이) 꺼져 있어도 시연할 수 있게, 대표 건물 5곳은 demo/
# fixtures/demo_snapshots.json의 고정값을 돌려준다(건물 자체는 실제 DB에 적재돼 있어야 함).
DEMO_MODE = env.bool("DEMO_MODE", default=False)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "rest_framework",
    "corsheaders",
    "django_celery_beat",
    # 공용
    "core",
    # 도메인 (CLAUDE.md 디렉터리 구조)
    "buildings",
    "satellite",
    "publicdata",
    "crime",
    "reports",
    "accounts",
    "favorites",
    "layers",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # gunicorn은 정적 파일을 안 서빙한다(runserver와 다름) — admin CSS/JS가 하나도
    # 안 불러와지는 걸로 실측 확인됨. WhiteNoise가 STATIC_ROOT를 직접 서빙한다.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- 데이터베이스: PostgreSQL + PostGIS (3-0: 벡터는 EPSG:4326 geometry로 저장) ---
DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="db"),
        "PORT": env("POSTGRES_PORT", default="5432"),
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# backend/ 전체가 ./backend:/app/backend로 볼륨 마운트돼 있어, BASE_DIR 밑에 두면 collectstatic
# 결과가 호스트 저장소에까지 쌓인다 — 마운트 밖(BASE_DIR.parent)에 둬서 컨테이너 안에만 남긴다.
STATIC_ROOT = BASE_DIR.parent / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- CORS ---
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

# --- Redis: 논리 DB 분리 (broker=/0, result backend=/1, cache·lock=/2) ---
REDIS_URL = env("REDIS_URL", default="redis://redis:6379")
REDIS_BROKER_URL = f"{REDIS_URL}/0"
REDIS_RESULT_BACKEND_URL = f"{REDIS_URL}/1"
REDIS_CACHE_URL = f"{REDIS_URL}/2"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
    }
}

# --- DRF ---
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "config.exceptions.jigwan_exception_handler",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    # fail-closed 기본값(감사 결과 반영) — 로그인 필요 없는 API(검색·건물 조회·insight·
    # 레이어·헬스체크·로그인/회원가입)는 해당 뷰에서 permission_classes = [AllowAny]로
    # 명시적으로 뒤집는다. 새 뷰를 추가할 때 깜빡하면 기본이 "닫힘"이라 안전한 쪽으로 샌다.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # IP 기준 비로그인 요청 제한(spec 9-1). 뷰별로 throttle_scope로 선택해 쓴다.
    "DEFAULT_THROTTLE_RATES": {
        "insight": "60/min",
        "search": "30/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "SIGNING_KEY": env("JWT_SIGNING_KEY"),
}

# --- Celery: 큐 3개(io/cpu/gpu) + 라우팅 안 된 잡이 빠지는 함정 큐("unrouted", 아무 워커도
# 구독하지 않음). 원래는 이 기본 큐 이름을 아예 선언 안 해서 디스패치 시점에 KeyError가 나게
# 했는데, 실제로 .delay()를 호출해보니(gpt-oss 리포트 생성 실측) Celery 5.4의
# amqp._create_task_sender가 라우팅 여부와 무관하게 task_default_queue를 미리 조회해서
# *라우팅이 멀쩡한 잡까지 전부* KeyError로 깨졌다. 그래서 "unrouted" 큐를 실제로 선언해
# 디스패치 자체는 살리고, 대신 core/tests/test_celery_routing.py가 등록된 모든 잡이
# CELERY_TASK_ROUTES에 있는지 정적으로 검사해 같은 실수를 테스트 시점에 잡는다.
CELERY_BROKER_URL = REDIS_BROKER_URL
CELERY_RESULT_BACKEND = REDIS_RESULT_BACKEND_URL
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_DEFAULT_QUEUE = "unrouted"
CELERY_TASK_CREATE_MISSING_QUEUES = False
CELERY_TASK_QUEUES = (
    Queue("io"),
    Queue("cpu"),
    Queue("gpu"),
    Queue("unrouted"),  # 아무 worker-*도 이 이름의 큐를 구독하지 않는다(docker-compose.yml)
)
# 이후 배치 잡은 spec 5-1 표에 맞춰 한 줄씩 추가한다. 빠뜨리면 test_celery_routing.py가 잡는다.
CELERY_TASK_ROUTES = {
    "core.tasks.healthcheck_ping": {"queue": "io"},
    "publicdata.tasks.trade_sync": {"queue": "io"},
    "publicdata.tasks.trigger_trade_sync_for_enabled_regions": {"queue": "io"},
    "satellite.tasks.satellite_collect": {"queue": "io"},
    "satellite.tasks.trigger_satellite_collect_for_enabled_regions": {"queue": "io"},
    "satellite.tasks.season_composite": {"queue": "cpu"},
    "satellite.tasks.change_analysis": {"queue": "cpu"},
    "satellite.tasks.region_stat_task": {"queue": "cpu"},
    "satellite.tasks.catalog_publish": {"queue": "cpu"},
    "satellite.tasks.trigger_season_chain_for_last_season": {"queue": "cpu"},
    "crime.tasks.safety_sync": {"queue": "io"},
    "crime.tasks.trigger_safety_sync_for_enabled_regions": {"queue": "io"},
    "reports.tasks.generate_report": {"queue": "gpu"},
    # 정리(보관 기한) 잡 — 외부 호출 없는 로컬 DB·파일 정리라 cpu 큐(감사 결과 반영).
    "core.tasks.cleanup_index_runs_task": {"queue": "cpu"},
    "satellite.tasks.cleanup_scene_cogs_task": {"queue": "cpu"},
}
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# --- 위성 장면 COG 저장 위치(TiTiler가 서빙하는 결과 COG와 다름 — 90일 보관용 임시 산출물) ---
SATELLITE_SCENE_COG_DIR = env(
    "SATELLITE_SCENE_COG_DIR", default=str(BASE_DIR.parent / "data" / "satellite_scenes")
)

# --- 계절 합성·변화 분석 결과 COG 저장 위치(영구 보관, TiTiler가 서빙하는 docker/data/cog 재사용) ---
RESULT_COG_DIR = env(
    "RESULT_COG_DIR", default=str(BASE_DIR.parent / "docker" / "data" / "cog")
)

# --- 외부 서비스(이번 단계는 미사용, 이후 단계에서 참조) ---
CDSE_S3_ACCESS_KEY = env("CDSE_S3_ACCESS_KEY", default="")
CDSE_S3_SECRET_KEY = env("CDSE_S3_SECRET_KEY", default="")
CDSE_S3_ENDPOINT = env("CDSE_S3_ENDPOINT", default="")
DATA_GO_KR_API_KEY = env("DATA_GO_KR_API_KEY", default="")
SAFEMAP_API_KEY = env("SAFEMAP_API_KEY", default="")
LLM_BASE_URL = env("LLM_BASE_URL", default="")
LLM_MODEL = env("LLM_MODEL", default="")
# 로컬 Ollama 실행은 vLLM(GPU)보다 느릴 수 있어 넉넉히 둔다. 실측(CPU, gpt-oss:20b):
# 리포트 프롬프트 기준 약 12.6토큰/초 — max_tokens=4000이면 약 5분, 재시도 여유까지
# 감안해 480초로 둔다(사용자 결정 180초 → 실측 후 480초로 조정).
LLM_TIMEOUT_SECONDS = env.int("LLM_TIMEOUT_SECONDS", default=480)
TITILER_BASE_URL = env("TITILER_BASE_URL", default="")

# --- 생활안전지도 범죄주의구간(9단계) ---
# GetFeatureInfo의 숨은 FEATURE_COUNT 서버 상한. probe_crime_feature_cap으로 확인해 넣기
# 전에는 비워 두고, run_safety_sync는 이 값이 없으면 시작 전에 멈춘다(사용자 결정).
# env.int()는 .env에 빈 값("")이 있으면 int("")에서 바로 죽으므로, 문자열로 읽어 직접 바꾼다.
_crime_feature_cap_raw = env("CRIME_FEATURE_CAP", default="")
CRIME_FEATURE_CAP = int(_crime_feature_cap_raw) if _crime_feature_cap_raw else None
# 운영자가 포털에서 확인한 실제 데이터 기간(예: "2023-07/2024-06"). GetFeatureInfo 응답에는
# 날짜 필드가 없어 매년 사람이 확인해 넣어야 한다.
CRIME_DATA_PERIOD = env("CRIME_DATA_PERIOD", default="")
# 생활안전지도 WMS GetMap 타일 중계 디스크 캐시(spec 10-3, TTL 30일).
CRIME_TILE_CACHE_DIR = env(
    "CRIME_TILE_CACHE_DIR", default=str(BASE_DIR.parent / "docker" / "data" / "crime_tiles")
)
