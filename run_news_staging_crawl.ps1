# =============================================================================
# VESTA RUN NEWS STAGING CRAWL - WINDOWS POWERSHELL RUNNER
# =============================================================================
# Cào tin tức độc lập vào database tạm: d:\VESTA\db\vesta_news_staging.duckdb
# Chống khóa tuyệt đối, không ảnh hưởng đến database chính (vesta_snapshot.duckdb)
# =============================================================================

param (
    [string]$DbPath = "d:/VESTA/db/vesta_news_staging.duckdb",
    [int]$NhanDanArticles = 5000,
    [int]$VnfPages = 50,
    [int]$TbtcPages = 50,
    [switch]$AutoMerge
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$PythonExe = "$ScriptDir\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "       VESTA INDEPENDENT NEWS CRAWLER (STAGING ISOLATED RUNNER)       " -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Cơ sở dữ liệu tạm thời : $DbPath" -ForegroundColor White
Write-Host "Báo Nhân Dân (2024->15): $NhanDanArticles bài tối đa" -ForegroundColor White
Write-Host "VietnamFinance         : $VnfPages trang / 6 chuyên mục" -ForegroundColor White
Write-Host "Thời báo Tài chính VN  : $TbtcPages trang API offset" -ForegroundColor White
Write-Host "Tự động Merge sau cào  : $(if ($AutoMerge) { 'BẬT' } else { 'TẮT (chạy thủ công)' })" -ForegroundColor White
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. Báo Nhân Dân (2024 -> 2015)
Write-Host "`n>>> [1/3] Khởi chạy Báo Nhân Dân (Sitemap 2024 -> 2015) <<<" -ForegroundColor Green
& $PythonExe -m src.crawlers.nhandan_crawler --db $DbPath --start-year 2024 --end-year 2015 --max-articles $NhanDanArticles --max-sitemaps 120

# 2. VietnamFinance (50 trang x 6 chuyên mục)
Write-Host "`n>>> [2/3] Khởi chạy VietnamFinance (50 trang / 6 chuyên mục) <<<" -ForegroundColor Green
& $PythonExe -m src.crawlers.vietnamfinance_crawler --db $DbPath --max-pages $VnfPages --max-articles 3000

# 3. Thời báo Tài chính Việt Nam
Write-Host "`n>>> [3/3] Khởi chạy Thời báo Tài chính Việt Nam (API offset) <<<" -ForegroundColor Green
& $PythonExe -m src.crawlers.thoibaotaichinh_crawler --db $DbPath --max-pages $TbtcPages --max-articles 3000

# 4. Tùy chọn tự động Merge vào kho chính
if ($AutoMerge) {
    Write-Host "`n>>> [TỰ ĐỘNG] Đồng bộ dữ liệu tạm vào kho chính (vesta_snapshot.duckdb) <<<" -ForegroundColor Magenta
    & $PythonExe -m src.etl.merge_news_staging
}

Write-Host "`n======================================================================" -ForegroundColor Cyan
Write-Host "  HOÀN TẤT QUÁ TRÌNH CÀO TIN TỨC VÀO CƠ SỞ DỮ LIỆU TẠM THỜI!          " -ForegroundColor Yellow
Write-Host "  Để gộp dữ liệu vào kho chính, vui lòng chạy:                        " -ForegroundColor White
Write-Host "  python -m src.etl.merge_news_staging                                " -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan
