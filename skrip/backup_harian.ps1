param([switch]$Penuh, [string]$Tujuan = "")
$ErrorActionPreference = "Stop"
$Akar = Split-Path -Parent $PSScriptRoot
if (-not $Tujuan) { $Tujuan = Join-Path $Akar "backup" }
New-Item -ItemType Directory -Force -Path $Tujuan | Out-Null
$Log = Join-Path $Tujuan "backup.log"
function Tulis($t) {
  $b = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $t
  Write-Host $b
  Add-Content -Path $Log -Value $b -Encoding UTF8
}

$Ini = Join-Path $Akar "server\pengaturan_dashboard.ini"
$cfg = @{}; $bagian = ""
foreach ($baris in Get-Content $Ini -Encoding UTF8) {
  $b = $baris.Trim()
  if ($b -match '^\[(.+)\]$') { $bagian = $Matches[1]; continue }
  if ($bagian -eq "mysql" -and $b -match '^([^;#=]+?)\s*=\s*(.*)$') { $cfg[$Matches[1].Trim()] = $Matches[2].Trim() }
}
$db = if ($cfg["database"]) { $cfg["database"] } else { "gpi_monitoring_system" }
$hostDb = if ($cfg["host"]) { $cfg["host"] } else { "127.0.0.1" }
$port = if ($cfg["port"]) { $cfg["port"] } else { "3306" }

$dump = $null
$c = Get-Command mysqldump.exe -ErrorAction SilentlyContinue
if ($c) { $dump = $c.Source }
if (-not $dump) {
  $dump = Get-ChildItem "C:\Program Files\MySQL" -Recurse -Filter mysqldump.exe -ErrorAction SilentlyContinue |
          Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $dump) { Tulis "GAGAL: mysqldump.exe tidak ditemukan (biasanya di C:\Program Files\MySQL\MySQL Server 8.4\bin)"; exit 1 }

$env:MYSQL_PWD = $cfg["password"]
$opsi = @("--host=$hostDb", "--port=$port", "--user=$($cfg['user'])", "--single-transaction", "--no-tablespaces",
          "--skip-triggers", "--default-character-set=utf8mb4")
if ((& $dump --help 2>$null) -match "set-gtid-purged") { $opsi += "--set-gtid-purged=OFF" }

function Dump($nama, $argTambahan) {
  $sql = Join-Path $Tujuan ($nama + ".sql")
  $t0 = Get-Date
  & $dump @opsi @argTambahan "--result-file=$sql"
  if ($LASTEXITCODE -ne 0) { throw "mysqldump gagal (kode $LASTEXITCODE) untuk $nama" }
  $zip = Join-Path $Tujuan ($nama + ".zip")
  Compress-Archive -Path $sql -DestinationPath $zip -Force
  Remove-Item $sql
  Tulis ("OK {0}.zip  {1:N1} MB  {2:N0} detik" -f $nama, ((Get-Item $zip).Length / 1MB), ((Get-Date) - $t0).TotalSeconds)
}

$tgl = Get-Date -Format "yyyyMMdd_HHmm"
try {
  if ($Penuh -or (Get-Date).DayOfWeek -eq "Sunday") {
    Dump "${db}_penuh_$tgl" @("--databases", $db)
  } else {
    Dump "${db}_harian_$tgl" @("--ignore-table=$db.telemetri", $db)
    Dump "${db}_telemetri2hari_$tgl" @("--no-create-info", "--where=waktu >= NOW() - INTERVAL 2 DAY", $db, "telemetri")
  }
} catch {
  Tulis ("GAGAL: " + $_.Exception.Message)
  exit 1
} finally {
  Remove-Item Env:\MYSQL_PWD -ErrorAction SilentlyContinue
}

Get-ChildItem $Tujuan -Filter "*_harian_*.zip" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } | Remove-Item
Get-ChildItem $Tujuan -Filter "*_telemetri2hari_*.zip" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } | Remove-Item
Get-ChildItem $Tujuan -Filter "*_penuh_*.zip" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-35) } | Remove-Item
exit 0
