# 读 Sabaki 盘面 -> 用引擎算一手 -> 点回 Sabaki
# 用法: powershell -File D:\Go\sabaki_reply.ps1 -Color b -Visits 150
param(
  [string]$Color = 'b',
  [int]$Visits = 150,
  [switch]$DryRun
)
$ErrorActionPreference = 'Continue'
$env:PYTHONIOENCODING = 'utf-8'
$py = 'D:\Anaconda3\python.exe'
$bot = 'D:\Go\sabaki_bot.py'
$state = 'D:\Go\sabaki_state.json'
$letters = 'ABCDEFGHJKLMNOPQRST'

# 1) 读盘
$null = & $py $bot read | Out-Null
if (-not (Test-Path $state)) { Write-Output 'READ_FAILED'; exit 1 }
$s = Get-Content $state -Raw -Encoding UTF8 | ConvertFrom-Json
$size = [int]$s.size
$stones = @($s.stones)
Write-Output ("盘面: {0} 路, {1} 子" -f $size, $stones.Count)

$b = @(); $w = @()
foreach ($st in $stones) {
  $i = [int]$st[0]; $j = [int]$st[1]; $c = [string]$st[2]
  $coord = $letters[$i] + [string]($size - $j)
  if ($c -eq 'B') { $b += $coord } else { $w += $coord }
  Write-Output ("   {0} = {1}" -f $coord, $c)
}

# 2) 还原着法顺序(交替制:黑先;无提子时成立;有提子时以盘面为准则跳过)
$moves = @()
$nb = $b.Count; $nw = $w.Count
$maxn = [Math]::Max($nb, $nw)
for ($k = 0; $k -lt $maxn; $k++) {
  if ($k -lt $nb) { $moves += $b[$k] }
  if ($k -lt $nw) { $moves += $w[$k] }
}
$moveStr = ($moves -join ',')
Write-Output ("着法序列(推断): " + $moveStr)

# 3) 引擎算一手
$json = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'D:\Go\move.ps1' -Moves $moveStr -Color $Color -Visits $Visits -TopN 5
Write-Output '--- 引擎结果 ---'
Write-Output $json
try { $r = $json | ConvertFrom-Json } catch { Write-Output 'ENGINE_PARSE_FAILED'; exit 1 }
$mv = $r.engine_move
if (-not $mv) { Write-Output 'ENGINE_NO_MOVE'; exit 1 }

# 4) 落到 Sabaki
if (-not $DryRun) {
  & $py $bot click $mv
  Write-Output ("已落子: " + $mv)
} else {
  Write-Output ("(dry-run) 应下: " + $mv)
}
