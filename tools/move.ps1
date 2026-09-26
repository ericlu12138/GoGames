# 叫一手:给定位局面,返回 KataGo 推荐着法 + 胜率/目差 + 候选点
# 用法: powershell -File D:\Go\move.ps1 -Moves "Q16,D4,Q4" -Color w -Visits 300
param(
  [string]$Moves = '',
  [string]$Color = 'w',
  [int]$Visits = 300,
  [int]$TopN = 5,
  [int]$Size = 19
)
$ErrorActionPreference = 'Continue'
$kg  = 'D:\Go\KataGo-opencl'
$net = Join-Path $kg 'kata1-tf3-b11c768-s11500M-d6163M.bin.gz'
$cfg = Join-Path $kg 'gtp_practice.cfg'

$cmds = New-Object System.Collections.ArrayList
[void]$cmds.Add("boardsize $Size")
[void]$cmds.Add('komi 7.5')
$i = 1
foreach ($m in ($Moves -split ',')) {
  $t = $m.Trim()
  if (-not $t) { continue }
  $c = if ($i % 2 -eq 1) { 'b' } else { 'w' }
  [void]$cmds.Add("play $c $t")
  $i++
}
[void]$cmds.Add("kata-genmove_analyze $Color interval 100 maxmoves $TopN")
[void]$cmds.Add('quit')

$sw = [Diagnostics.Stopwatch]::StartNew()
$out = ($cmds -join "`n") | & (Join-Path $kg 'katago.exe') gtp -model $net -config $cfg 2>&1
$el = [Math]::Round($sw.Elapsed.TotalSeconds, 1)

# 着法:KataGo 新版输出 "play XXX";兼容旧版 "= XXX"
$move = ''
$pl = $out | Where-Object { $_ -match '^play\s+[A-Ta-t][0-9]{1,2}' } | Select-Object -Last 1
if ($pl) { $move = ($pl -replace '^play\s+', '').Trim() }
else {
  $mv = $out | Where-Object { $_ -match '^=\s*[A-T][0-9]{1,2}' } | Select-Object -Last 1
  if ($mv) { $move = ($mv -replace '^=\s*', '').Trim() }
}

$infos = @($out | Where-Object { $_ -match '^info ' })
$last  = $infos | Select-Object -Last 1
$first = $infos | Select-Object -First 1
$winrate = $null; $scoreLead = $null; $visits = $null; $pv = ''
if ($last) {
  if ($last -match 'winrate\s+([0-9.]+)')   { $winrate   = [double]$Matches[1] }
  if ($last -match 'scoreLead\s+(-?[0-9.]+)') { $scoreLead = [double]$Matches[1] }
  if ($last -match 'visits\s+(\d+)')        { $visits    = [int]$Matches[1] }
  if ($last -match 'pv\s+((?:[A-T][0-9]{1,2}\s*){1,10})') { $pv = $Matches[1].Trim() }
}
$cands = @()
if ($first) {
  $segs = $first -split 'info move '
  for ($k = 1; $k -lt $segs.Count; $k++) {
    $seg = $segs[$k]
    $mvName = ($seg -split '\s+')[0]
    if ($mvName -notmatch '^[A-T][0-9]{1,2}$') { continue }
    $w = [regex]::Match($seg, 'winrate\s+([0-9.]+)')
    $s = [regex]::Match($seg, 'scoreLead\s+(-?[0-9.]+)')
    $v = [regex]::Match($seg, 'visits\s+(\d+)')
    $cands += [pscustomobject]@{
      move      = $mvName
      visits    = if ($v.Success) { [int]$v.Groups[1].Value } else { 0 }
      winrate   = if ($w.Success) { [double]$w.Groups[1].Value } else { $null }
      scoreLead = if ($s.Success) { [double]$s.Groups[1].Value } else { $null }
    }
  }
}

[ordered]@{
  to_move      = $Color
  engine_move  = $move
  winrate      = $winrate
  scoreLead    = $scoreLead
  pv           = $pv
  root_visits  = $visits
  candidates   = $cands
  elapsed_sec  = $el
} | ConvertTo-Json -Depth 5
