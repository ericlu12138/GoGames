param([int]$Target = 1, [int]$Hours = 4)
$p = "F:\围棋\外接AI\position.txt"
$mv = "F:\围棋\外接AI\ai_move.txt"
$deadline = (Get-Date).AddHours($Hours)
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Milliseconds 700
  if (-not (Test-Path $p)) { continue }
  $t = Get-Content $p -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
  if (-not $t) { continue }
  if ($t -match '当前第\s*(\d+)\s*手') {
    $n = [int]$Matches[1]
    if ($n -gt $Target) { break }            # 已经过号,静默退出
    if ($n -eq $Target -and ($n % 2 -eq 1) -and -not (Test-Path $mv) -and ($t -match 'ai_move\.txt')) {
      Start-Sleep -Seconds 1
      "=== 轮到我(白):当前 $n 手,该我落第 $($n+1) 手 ==="
      Get-Content $p -Raw -Encoding UTF8
      break
    }
  }
}