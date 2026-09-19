# run_crawl_all_ohlcv_fundamentals.ps1
# Script PowerShell cào toàn bộ Dữ liệu Giá (OHLCV) và Báo cáo tài chính (BCTC) trên Vnstock cho VESTA
# Hỗ trợ tự động chạy trong Virtual Environment (.venv), chống lock file database trên Windows.

param (
    [string]$Mode = "all",           # "all", "ohlcv", "fundamentals"
    [string]$Symbols = "all",        # "all" (1,522 mã niêm yết), "vn30", hoặc danh sách "VCB,TCB,HPG"
    [string]$Period = "quarter",     # "quarter" hoặc "year" (cho BCTC)
    [double]$Delay = 0.4,            # Độ trễ giữa các mã (giây)
    [switch]$Force,                  # Bắt buộc cào lại, không bỏ qua mã đã hoàn thành
    [switch]$Background              # Chạy ngầm không chặn cửa sổ console
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "Không tìm thấy .venv/Scripts/python.exe. Sử dụng python hệ thống..." -ForegroundColor Yellow
    $VenvPython = "python"
}

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "         VESTA QUANT LAKEHOUSE - TIẾN TRÌNH CÀO OHLCV & FUNDAMENTALS            " -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "Thư mục dự án: $ProjectRoot" -ForegroundColor Gray
Write-Host "Python:        $VenvPython" -ForegroundColor Gray
Write-Host "Chế độ cào:    $Mode" -ForegroundColor Yellow
Write-Host "Danh mục mã:   $Symbols" -ForegroundColor Yellow
Write-Host "Kỳ BCTC:       $Period" -ForegroundColor Gray
Write-Host "Độ trễ (Delay): $Delay s" -ForegroundColor Gray
Write-Host "Cờ Force:      $($Force.IsPresent)" -ForegroundColor Gray
Write-Host "--------------------------------------------------------------------------------" -ForegroundColor Gray

$ArgsList = @(
    "-m", "src.crawlers.crawl_all_ohlcv_fundamentals",
    "--mode", $Mode,
    "--symbols", $Symbols,
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
$LogFile = Join-Path $LogDir "crawl_${Mode}_${Timestamp}.log"

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
