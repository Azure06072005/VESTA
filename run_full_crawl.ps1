# =============================================================================
# VESTA RUN FULL CRAWL - WINDOWS POWERSHELL RUNNER
# =============================================================================
# Script tự động kích hoạt môi trường ảo và chạy toàn bộ pipeline thu thập dữ liệu:
# 1. Báo cáo tài chính & chỉ số định lượng (vnstock, CafeF, Vietstock, thuyết minh, tự doanh, khối ngoại, vĩ mô, giá).
# 2. Toàn bộ tin tức & chính sách (tin doanh nghiệp, cổng thông tin tài chính, văn bản quy phạm vĩ mô, hiệp hội ngành).
# 3. Tự động đồng bộ và mở Dashboard theo dõi tiến trình.
#
# Cách dùng:
#   .\run_full_crawl.ps1                    # Chạy mặc định cho rổ VN30 (khuyên dùng)
#   .\run_full_crawl.ps1 -Scope all         # Cào toàn bộ 1,750 mã niêm yết
#   .\run_full_crawl.ps1 -SmokeTest         # Chạy thử nghiệm nhanh (2 mã)
#   .\run_full_crawl.ps1 -Force             # Bắt buộc cào lại toàn bộ (không skip)
# =============================================================================

param (
    [string]$Scope = "vn30",
    [string]$Mode = "all",
    [string]$Priority = "both",
    [int]$TargetEarliestYear = 2000,
    [switch]$Force,
    [switch]$SmokeTest,
    [double]$Delay = 0.5
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Xác định trình thông dịch Python
$PythonExe = "$ScriptDir\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "            VESTA AUTONOMOUS TRADING - FULL CRAWL RUNNER              " -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Python Path          : $PythonExe" -ForegroundColor Gray
Write-Host "Phạm vi cào (Scope)  : $Scope" -ForegroundColor White
Write-Host "Chế độ (Mode)        : $Mode" -ForegroundColor White
Write-Host "Chiến lược ngày      : $Priority (Năm sớm nhất: $TargetEarliestYear)" -ForegroundColor White
Write-Host "Chế độ Force         : $(if ($Force) { 'BẬT (Cào lại toàn bộ)' } else { 'TẮT (Tự động Skip mã/ngày đã có)' })" -ForegroundColor White
Write-Host "Smoke Test           : $(if ($SmokeTest) { 'BẬT' } else { 'TẮT' })" -ForegroundColor White
Write-Host "======================================================================" -ForegroundColor Cyan

$CmdArgs = @(
    "-m", "src.crawlers.run_full_crawling_pipeline",
    "--scope", $Scope,
    "--mode", $Mode,
    "--priority", $Priority,
    "--target-earliest-year", $TargetEarliestYear,
    "--delay", $Delay
)

if ($Force) {
    $CmdArgs += "--force"
}
if ($SmokeTest) {
    $CmdArgs += "--smoke-test"
}

& $PythonExe $CmdArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[!] Quá trình cào dữ liệu gặp lỗi (Mã thoát: $LASTEXITCODE)." -ForegroundColor Red
    exit $LASTEXITCODE
} else {
    Write-Host "`n[OK] Toàn bộ dữ liệu đã được cào và nạp vào DuckDB thành công!" -ForegroundColor Green
}
