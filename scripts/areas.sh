#!/usr/bin/env bash
# manage.py areas 래퍼(다지역 지원 10단계). Git Bash/WSL/맥/리눅스용 — Windows PowerShell은
# areas.ps1을 쓴다.
#
# 사용법:
#   ./scripts/areas.sh                                  대화형 메뉴
#   ./scripts/areas.sh list|status|available|add|enable|disable|sync ...   그대로 전달
#   ./scripts/areas.sh sync --area 36 --background       컨테이너 안에서 분리 실행(로그는 파일로)
#   ./scripts/areas.sh logs 36                           위 로그를 tail -f
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ "$#" -eq 0 ]; then
    exec docker compose exec -it api python manage.py areas
fi

if [ "$1" = "logs" ]; then
    area="${2:-}"
    if [ -z "$area" ]; then
        echo "사용법: $0 logs <시도코드>" >&2
        exit 1
    fi
    # 앞에 슬래시를 하나 더 붙인다 — Git Bash(MSYS)가 "/app/..." 같은 단독 인자를
    # 리눅스 컨테이너 안 경로가 아니라 윈도우 경로로 오인해 "C:/Program Files/Git/app/..."로
    # 바꿔버리는 걸 막는다(실측 확인). 리눅스 컨테이너 안에서는 "//"가 "/"와 같게 처리된다.
    exec docker compose exec api tail -f "//app/logs/sync_${area}.log"
fi

background=0
area=""
args=()
prev=""
for arg in "$@"; do
    if [ "$arg" = "--background" ]; then
        background=1
    else
        args+=("$arg")
        if [ "$prev" = "--area" ]; then
            area="$arg"
        fi
    fi
    prev="$arg"
done

if [ "$background" -eq 1 ]; then
    if [ -z "$area" ]; then
        echo "--background는 --area <시도코드>가 필요합니다." >&2
        exit 1
    fi
    if ! [[ "$area" =~ ^[A-Za-z0-9_-]+$ ]]; then
        echo "--area 값이 올바르지 않습니다: $area" >&2
        exit 1
    fi
    log_path="//app/logs/sync_${area}.log"  # Git Bash(MSYS) 경로 오인 방지(위 logs와 같은 이유)
    printf -v cmd_str '%q ' python manage.py areas "${args[@]}"
    docker compose exec -d api sh -c "${cmd_str}>> ${log_path} 2>&1"
    echo "백그라운드로 실행했습니다. 로그: ./scripts/areas.sh logs ${area}"
else
    exec docker compose exec api python manage.py areas "${args[@]}"
fi
