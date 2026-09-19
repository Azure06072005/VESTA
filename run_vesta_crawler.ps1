# run_vesta_crawler.ps1
# VESTA UNIFIED CRAWLER CONTROLLER (PowerShell Automation Suite)
# Hỗ trợ 3 tác vụ chính:
# 1. -Action status : Quét toàn bộ Lakehouse, kiểm tra min_date, max_date, số lượng bản ghi và độ trễ.
# 2. -Action latest : Cào cập nhật bù tiến đến hôm nay cho toàn bộ thị trường.
# 3. -Category <name> : Cào độc lập duy nhất 1 phân hệ lựa chọn (ohlcv, fundamentals, news, news_macro, events, macro, governance).

param (
    [string]$Action = "status",        # "status", "latest", "crawl"
    [string]$Category = "",            # "ohlcv", "fundamentals", "news", "news_macro", "events", "macro", "governance"
    [string]$Symbols = "all",          # "all" (1,522 mã niêm yết), "vn30", hoặc danh sách "VCB,TCB,HPG"
    [string]$Interval = "1D",          # "1D" (nến ngày) hoặc "1m" (nến phút)
    [string]$Period = "quarter",       # "quarter" hoặc "year" (cho BCTC)
    [double]$Delay = 0.4,              # Thời gian nghỉ giữa các mã (giây)
    [switch]$Force,                    # Bắt buộc cào đè, bỏ qua checkpoint
    [switch]$Background                # Chạy nền không chặn terminal
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "Không tìm thấy .venv/Scripts/python.exe. Dùng python hệ thống..." -ForegroundColor Yellow
    $VenvPython = "python"
}

# 1. Xử lý Action = status
if ($Action -eq "status" -or $Action -eq "check") {
    & $VenvPython -m src.crawlers.vesta_crawler_cli status
    exit 0
}

# 2. Xử lý cào dữ liệu
$ArgsList = @("-m", "src.crawlers.vesta_crawler_cli", "crawl")

if ($Category -ne "") {
    $ArgsList += @("--mode", "category", "--category", $Category)
} elseif ($Action -eq "latest") {
    $ArgsList += @("--mode", "latest")
} else {
    $ArgsList += @("--mode", "all")
}

$ArgsList += @(
    "--symbols", $Symbols,
    "--interval", $Interval,
    "--period", $Period,
    "--delay", $Delay
)

if ($Force.IsPresent) {
    $ArgsList += "--force"
}

$LogDir = Join-Path $ProjectRoot "out\logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$TargetName = if ($Category -ne "") { $Category } else { $Action }
$LogFile = Join-Path $LogDir "vesta_${TargetName}_${Timestamp}.log"

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "                 VESTA UNIFIED CRAWLER ORCHESTRATOR HUB                         " -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "Tác vụ:        $Action" -ForegroundColor Yellow
if ($Category -ne "") {
    Write-Host "Phân hệ chọn:  $Category" -ForegroundColor Yellow
}
Write-Host "Danh mục mã:   $Symbols" -ForegroundColor Gray
Write-Host "Khung nến:     $Interval" -ForegroundColor Gray
Write-Host "Độ trễ:        $Delay s" -ForegroundColor Gray
Write-Host "Cờ Force:      $($Force.IsPresent)" -ForegroundColor Gray
Write-Host "--------------------------------------------------------------------------------" -ForegroundColor Gray

if ($Background.IsPresent) {
    Write-Host "Khởi chạy tiến trình cào NGẦM..." -ForegroundColor Green
    Write-Host "File log theo dõi: $LogFile" -ForegroundColor Green
    Start-Process -FilePath $VenvPython -ArgumentList $ArgsList -RedirectStandardOutput $LogFile -RedirectStandardError $LogFile -WindowStyle Hidden
    Write-Host "Tiến trình đã được đẩy vào chạy nền thành công!" -ForegroundColor Green
    Write-Host "Để theo dõi tiến độ thời gian thực, hãy chạy:" -ForegroundColor Cyan
    Write-Host "Get-Content -Path '$LogFile' -Wait -Tail 30" -ForegroundColor White
} else {
    Write-Host "Bắt đầu thực thi trực tiếp trên console..." -ForegroundColor Green
    & $VenvPython $ArgsList
}
