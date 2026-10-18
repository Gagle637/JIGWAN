FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# GDAL/GEOS/PROJ: django.contrib.gis + rasterio/geopandas/shapely 빌드·런타임 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 빌드 시점에 GDAL이 실제로 깔렸는지 바로 확인(링크가 깨지면 여기서 빌드가 실패한다)
RUN gdalinfo --version

WORKDIR /app/backend

COPY backend/requirements/base.txt requirements/base.txt
COPY backend/requirements/dev.txt requirements/dev.txt
RUN pip install --no-cache-dir -r requirements/dev.txt

# django.contrib.gis가 ctypes로 같은 GDAL을 찾는지도 확인(settings 없이 최소 구성으로)
RUN python -c "import django; from django.conf import settings; settings.configure(); \
from django.contrib.gis.gdal import gdal_version; print('GeoDjango sees GDAL', gdal_version())"

COPY backend/ /app/backend/

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
