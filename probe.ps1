param(
    [Parameter(Position=0)]
    [string]$Index,
    [switch]$Step,
    [switch]$Reset,
    [int[]]$Range,
    [int]$DelayMs = 500
)

$file = "C:\Users\Tail\test_led.txt"

if ($Reset) {
    if (Test-Path $file) { Remove-Item $file }
    Write-Host "Probe reset: normal OpenRGB control restored." -ForegroundColor Green
    return
}

if ($Step) {
    $candidates = 1..200 | ForEach-Object { @{ Id = $_; Name = "LED $_" } }

    Write-Host "=== Lightbar Candidate Stepping ===" -ForegroundColor Yellow
    foreach ($item in $candidates) {
        Set-Content $file $item.Id
        Write-Host "Lighting Index $($item.Id) ($($item.Name)). Observe the laptop front lightbar..." -ForegroundColor Cyan
        $null = Read-Host "Press Enter for next candidate"
    }

    if (Test-Path $file) { Remove-Item $file }
    Write-Host "Step testing completed. Restored normal control." -ForegroundColor Green
    return
}

if ($Range -and $Range.Length -ge 2) {
    $start = $Range[0]
    $end = $Range[1]
    Write-Host "Sweeping indices $start to $end with ${DelayMs}ms delay..." -ForegroundColor Cyan
    for ($i = $start; $i -le $end; $i++) {
        Set-Content $file $i
        Write-Host "Index $i lit..." -ForegroundColor Yellow
        Start-Sleep -Milliseconds $DelayMs
    }
    if (Test-Path $file) { Remove-Item $file }
    Write-Host "Sweep completed. Restored normal control." -ForegroundColor Green
    return
}

if ($Index -ne "") {
    Set-Content $file $Index
    Write-Host "Probe active: index $Index lit white." -ForegroundColor Yellow
} else {
    Write-Host "Usage:"
    Write-Host "  .\probe.ps1 <index>                 - Light a single index (e.g. .\probe.ps1 174)"
    Write-Host "  .\probe.ps1 -Step                   - Step through all lightbar candidates (167-179)"
    Write-Host "  .\probe.ps1 -Range 165,180          - Auto sweep range 165 to 180"
    Write-Host "  .\probe.ps1 -Reset                  - Turn off probe and restore normal lighting"
}
