# 0x44 STATUS. What is running on the ladder right now, at a glance.
# Usage:  powershell -ExecutionPolicy Bypass -File status.ps1
#     or: .\status.ps1
# The rig directory is the one this script sits in, so there is no
# machine-specific path and a clone works wherever it is checked out.
$rrc = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }

function Line($t) { Write-Host $t }
function Header($t) {
    Write-Host ""
    Write-Host ("  " + $t) -ForegroundColor Cyan
    Write-Host ("  " + ("-" * 66)) -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  ============ 0x44 LADDER -- STATUS $(Get-Date -Format 'HH:mm:ss') ============" -ForegroundColor White

# ---------- running processes ----------
Header "RUNNING NOW"
$py = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -EA SilentlyContinue)
$rng = @(Get-Process RNG_test -EA SilentlyContinue).Count
if ($py.Count -eq 0) {
    Line "  nothing: the machine is free"
} else {
    foreach ($p in $py) {
        $cmd = $p.CommandLine
        # These patterns are the subcommands of ladder.py. Before the
        # merge every stage had its own script, and the old patterns
        # ('diploma.py', 'depth_test') matched nothing afterwards. A
        # status display that says "python" while a diploma runs is
        # worse than none.
        $what = switch -Regex ($cmd) {
            # break after each: -Regex runs EVERY matching branch, and
            # the general 'ladder\.py' matches alongside the specific
            # one. Without it $what is an array and prints as
            # System.Object[].
            'ladder\.py diploma'      { "Diploma (RRC-64-40)"; break }
            'ladder\.py depth'        { "depth test 2^34"; break }
            'ladder\.py gauntlet'     { "deep gauntlet"; break }
            'ladder\.py anchor'       { "anchor measurement"; break }
            'ladder\.py cost'         { "cost class enumeration"; break }
            'ladder\.py exhaust'      { "K9 exhaustion"; break }
            'ladder\.py wyhash-depth' { "wyhash8 at depth"; break }
            'ladder\.py trial'        { "trial (stranger's mixer)"; break }
            'ladder\.py smoke'        { "smoke test"; break }
            'ladder\.py'              { "ladder"; break }
            default                   { "python" }
        }
        $min = [int]((New-TimeSpan -Start $p.CreationDate).TotalMinutes)
        Line ("  {0,-28} for {1,5} min   (PID {2})" -f $what, $min, $p.ProcessId)
    }
    Line ("  {0} test pairs active (RNG_test)" -f $rng)
}

# ---------- diploma meer10 ----------
$log = "$rrc\diploma40_meer10.log"
if (Test-Path $log) {
    Header "DIPLOMA meer10  (256 streams x 1 TB)"
    $ck = "$rrc\diploma40_meer10_ckpt.jsonl"
    if (Test-Path $ck) {
        $lines = @(Get-Content $ck)
        $fails = @($lines | Where-Object { $_ -match 'FAIL' })
        $pct = [math]::Round(100 * $lines.Count / 256, 1)
        Line ("  recorded: {0}/256  ({1} %)   FAIL: {2}" -f $lines.Count, $pct, $fails.Count)
        if ($fails.Count -gt 0) {
            Write-Host "  *** FAILED ***" -ForegroundColor Red
            $fails | Select-Object -Last 3 | ForEach-Object { Line ("    " + $_) }
        }
    } else {
        Line "  no stream recorded yet (the first one takes ~5-7 h)"
    }
    Get-Content $log | Select-String -CaseSensitive "/256\]|FAILED|DIPLOMA meer10:" |
        Select-Object -Last 4 | ForEach-Object { Line ("  " + $_.Line.Trim()) }
}

# ---------- wyhash8 ----------
$w = "$rrc\wyhash_depth_result.json"
$wl = "$rrc\wyhash_depth.log"
if ((Test-Path $w) -or (Test-Path $wl)) {
    Header "wyhash8 AT DEPTH"
    if (Test-Path $w) {
        $j = Get-Content $w -Raw | ConvertFrom-Json
        Write-Host ("  DONE: " + $j.conclusion) -ForegroundColor Green
        $j.runs.PSObject.Properties | ForEach-Object {
            Line ("    {0,-22} {1}" -f $_.Name, $_.Value) }
    } else {
        $active = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -EA SilentlyContinue |
                    Where-Object { $_.CommandLine -match 'wyhash_depth' }).Count
        $n = @(Get-Content $wl | Select-String -CaseSensitive "^  done:").Count
        if ($active -gt 0) {
            Line ("  running: {0} of 3 streams done" -f $n)
        } else {
            Write-Host "  PAUSED (no resume; a restart begins from scratch)" -ForegroundColor Yellow
        }
    }
}

# ---------- cost classes ----------
# One folder per campaign since 30.08.: results\k5\evals.jsonl and so
# on. The flat names (class_k5_evals.jsonl) are what the published
# archives are called, not what a running campaign writes.
foreach ($k in @("k5", "k6", "k10_l3")) {
    $ev = "$rrc\results\$k\evals.jsonl"
    if (Test-Path $ev) {
        Header ("COST CLASS " + $k.ToUpper().Replace("_L3", " (three-op core)"))
        $lines = @(Get-Content $ev)
        $passer = @($lines | Where-Object { $_ -match '"stage": "PASSER"' }).Count
        $smoke = @($lines | Where-Object { $_ -match 'smoke_dead' }).Count
        Line ("  evaluated: {0}   smoke reached: {1}   PASSER: {2}" -f $lines.Count, $smoke, $passer)
        if ($passer -gt 0) {
            Write-Host "  *** PASSER FOUND ***" -ForegroundColor Green
        }
    }
}

Write-Host ""
$live = @(Get-ChildItem "$rrc\*.log" -EA SilentlyContinue |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1)
if ($live.Count -gt 0) {
    Write-Host ("  Follow live:  Get-Content " + $live[0].FullName + " -Wait -Tail 5") -ForegroundColor DarkGray
} else {
    Write-Host "  No run log in $rrc yet." -ForegroundColor DarkGray
}
Write-Host ""
