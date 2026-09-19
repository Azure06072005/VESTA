# run_gui.ps1
# Khởi động ứng dụng giao diện Desktop VESTA Crawler Controller
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $VenvPython = "python"
}

Write-Host "Đang khởi động VESTA Desktop Crawler App..." -ForegroundColor Cyan
Start-Process -FilePath $VenvPython -ArgumentList "-m", "src.crawlers.vesta_crawler_gui"
