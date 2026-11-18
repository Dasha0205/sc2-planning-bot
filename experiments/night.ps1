# A night of series (T7.2): every line of the queue file is one run_batch.py
# command line; each series is played, then summarised with aggregate.py.
# A failed series is logged and the queue goes on. A rerun skips finished games.
#
#   powershell -File experiments/night.ps1 -Queue experiments/queue.txt
#
# queue.txt, one series per line ("#" starts a comment):
#   --name E5_numeric_Medium --map AbyssalReefLE --difficulty Medium --games 20 --seed 5220000

param(
    [Parameter(Mandatory = $true)][string]$Queue,
    [string]$Python
)

$repo = Resolve-Path "$PSScriptRoot\.."
if (-not $Python) { $Python = Join-Path $repo ".venv\Scripts\python.exe" }
$log = Join-Path $repo "runs\night_$(Get-Date -Format 'yyyy-MM-dd_HH-mm').log"

foreach ($line in Get-Content $Queue) {
    $line = ($line -split '#')[0].Trim()
    if (-not $line) { continue }
    $arguments = $line -split '\s+'
    $name = $arguments[[array]::IndexOf($arguments, '--name') + 1]

    "$(Get-Date -Format s) start $line" | Add-Content $log
    & $Python "$repo\experiments\run_batch.py" @arguments 2>&1 | Add-Content $log
    "$(Get-Date -Format s) batch exit $LASTEXITCODE" | Add-Content $log

    & $Python "$repo\experiments\aggregate.py" "$repo\runs\$name" 2>&1 | Add-Content $log
    "$(Get-Date -Format s) done $name" | Add-Content $log
}
