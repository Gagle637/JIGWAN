# manage.py areas 래퍼(다지역 지원 10단계). PowerShell용 — Git Bash/WSL/맥/리눅스는 areas.sh를 쓴다.
#
# 사용법:
#   .\scripts\areas.ps1                                  대화형 메뉴
#   .\scripts\areas.ps1 list|status|available|add|enable|disable|sync ...   그대로 전달
#   .\scripts\areas.ps1 sync --area 36 --background       컨테이너 안에서 분리 실행(로그는 파일로)
#   .\scripts\areas.ps1 logs 36                           위 로그를 tail -f

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CmdArgs
)

Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not $CmdArgs -or $CmdArgs.Count -eq 0) {
    docker compose exec -it api python manage.py areas
    exit $LASTEXITCODE
}

if ($CmdArgs[0] -eq "logs") {
    if ($CmdArgs.Count -lt 2) {
        Write-Error "사용법: areas.ps1 logs <시도코드>"
        exit 1
    }
    $area = $CmdArgs[1]
    docker compose exec api tail -f "/app/logs/sync_$area.log"
    exit $LASTEXITCODE
}

$background = $false
$area = $null
$passArgs = @()
for ($i = 0; $i -lt $CmdArgs.Count; $i++) {
    if ($CmdArgs[$i] -eq "--background") {
        $background = $true
    } else {
        $passArgs += $CmdArgs[$i]
        if ($CmdArgs[$i] -eq "--area" -and ($i + 1) -lt $CmdArgs.Count) {
            $area = $CmdArgs[$i + 1]
        }
    }
}

if ($background) {
    if (-not $area) {
        Write-Error "--background는 --area <시도코드>가 필요합니다."
        exit 1
    }
    if ($area -notmatch '^[A-Za-z0-9_-]+$') {
        Write-Error "--area 값이 올바르지 않습니다: $area"
        exit 1
    }
    $logPath = "/app/logs/sync_$area.log"
    $innerCmd = "python manage.py areas " + ($passArgs -join ' ') + " >> $logPath 2>&1"
    docker compose exec -d api sh -c $innerCmd
    Write-Host "백그라운드로 실행했습니다. 로그: .\scripts\areas.ps1 logs $area"
} else {
    docker compose exec api python manage.py areas @passArgs
    exit $LASTEXITCODE
}
