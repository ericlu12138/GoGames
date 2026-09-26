$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$dst = 'F:\Go'
New-Item -ItemType Directory -Force -Path "$dst\dl" | Out-Null
$netUrl = [string](Get-Content 'F:\Go\net_url.txt' -Raw)
if ($netUrl) { $netUrl = $netUrl.Trim() }
Write-Output ("net url = [" + $netUrl + "]")
$items = New-Object System.Collections.ArrayList
[void]$items.Add(@{ n = 'katago-v1.18.1-opencl-windows-x64.zip';    u = 'https://github.com/lightvector/KataGo/releases/download/v1.18.1/katago-v1.18.1-opencl-windows-x64.zip' })
[void]$items.Add(@{ n = 'katago-v1.18.1-eigenavx2-windows-x64.zip'; u = 'https://github.com/lightvector/KataGo/releases/download/v1.18.1/katago-v1.18.1-eigenavx2-windows-x64.zip' })
[void]$items.Add(@{ n = 'sabaki-v0.60.0-win-x64-setup.exe';         u = 'https://github.com/SabakiHQ/Sabaki/releases/download/v0.60.0/sabaki-v0.60.0-win-x64-setup.exe' })
if ($netUrl -like 'http*') { [void]$items.Add(@{ n = [System.IO.Path]::GetFileName($netUrl); u = $netUrl }) }
Write-Output ("待下载 " + $items.Count + " 个文件")
$wc = New-Object System.Net.WebClient
$wc.Headers.Add('User-Agent', 'Mozilla/5.0')
foreach ($it in $items) {
  $out = Join-Path "$dst\dl" $it.n
  if ((Test-Path $out) -and ((Get-Item $out).Length -gt 100KB)) { Write-Output ("skip: " + $it.n); continue }
  $sw = [Diagnostics.Stopwatch]::StartNew()
  try {
    $wc.DownloadFile($it.u, $out)
    Write-Output ("done: {0}  {1:N1} MB  {2:N0}s" -f $it.n, ((Get-Item $out).Length/1MB), $sw.Elapsed.TotalSeconds)
  } catch {
    Write-Output ("FAIL: " + $it.n + " :: " + $_.Exception.Message)
    try { if (Test-Path $out) { Remove-Item $out -Force } } catch {}
  }
}
Write-Output 'ALL DOWNLOADS FINISHED'