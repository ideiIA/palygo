# Cluster Postgres de desenvolvimento do PlayGo, isolado do servidor principal (5432) e do Licitacoes (5433).
# Uso: .\scripts\dev_db.ps1 [start|stop|status]
param([ValidateSet('start', 'stop', 'status')] [string]$Acao = 'start')

$ErrorActionPreference = 'Stop'
$porta = 5434
$pgCtl = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\pg_ctl.exe' | Sort-Object FullName -Descending | Select-Object -First 1
if (-not $pgCtl) { throw 'PostgreSQL nao encontrado em C:\Program Files\PostgreSQL' }
$bin = $pgCtl.DirectoryName
$raiz = Split-Path -Parent $PSScriptRoot
$dados = Join-Path $raiz '.pgdata'

if ($Acao -eq 'stop') { & "$bin\pg_ctl.exe" -D $dados -m fast stop; return }
if ($Acao -eq 'status') { & "$bin\pg_isready.exe" -h localhost -p $porta; return }

if (-not (Test-Path (Join-Path $dados 'PG_VERSION'))) {
    & "$bin\initdb.exe" -D $dados -U playgo -A trust -E UTF8 --locale=C | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'initdb falhou' }
}
& "$bin\pg_isready.exe" -h localhost -p $porta | Out-Null
if ($LASTEXITCODE -ne 0) {
    # Sem -Wait: no Windows o pg_ctl continua vivo como pai do servidor.
    Start-Process -FilePath "$bin\pg_ctl.exe" -WindowStyle Hidden `
        -ArgumentList '-D', "`"$dados`"", '-l', "`"$(Join-Path $dados 'server.log')`"", '-o', "`"-p $porta`"", 'start'
    foreach ($i in 1..120) {  # recuperacao apos queda pode levar mais de 30 s
        Start-Sleep -Seconds 1
        & "$bin\pg_isready.exe" -h localhost -p $porta | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
    }
    if ($LASTEXITCODE -ne 0) { throw "Postgres nao subiu na porta $porta (veja .pgdata\server.log)" }
}
$existe = & "$bin\psql.exe" -h localhost -p $porta -U playgo -d postgres -tAc "select 1 from pg_database where datname='playgo'"
if ($existe -ne '1') { & "$bin\createdb.exe" -h localhost -p $porta -U playgo -E UTF8 playgo }
& "$bin\pg_isready.exe" -h localhost -p $porta
