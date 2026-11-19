# Sobe os dois modulos da Calculadora oficial (perfil offline) em segundo plano:
#   regime regular   -> http://localhost:8080/api  (Swagger: /api/swagger-ui.html)
#   Simples Nacional -> http://localhost:8082/api
# Uso: powershell -ExecutionPolicy Bypass -File calculadora-oficial\executar.ps1 [-Parar]
param([switch]$Parar)

$ErrorActionPreference = "Stop"
$Destino = $PSScriptRoot
$Pids = Join-Path $Destino "base\pids.txt"

if ($Parar) {
    if (Test-Path $Pids) {
        Get-Content $Pids | ForEach-Object { try { Stop-Process -Id ([int]$_) -Confirm:$false } catch {} }
        Remove-Item $Pids -Confirm:$false
        Write-Host "Calculadora oficial parada."
    } else { Write-Host "Nenhum processo registrado." }
    return
}

$Modulos = @(
    @{ Pasta = "regime-regular";   Jar = "target\api-regime-geral.jar";     Porta = 8080 },
    @{ Pasta = "simples-nacional"; Jar = "target\api-simples-nacional.jar"; Porta = 8082 }
)
New-Item -ItemType Directory -Force (Join-Path $Destino "base") | Out-Null
$ids = @()
foreach ($m in $Modulos) {
    $dir = Join-Path $Destino $m.Pasta
    if (-not (Test-Path (Join-Path $dir $m.Jar))) { throw "JAR nao encontrado em $($m.Pasta) - rode instalar-github.ps1 antes." }
    # o JAR precisa rodar da raiz do modulo para achar .\calculadora\db\calculadora-pro.db
    $p = Start-Process java -ArgumentList "-Dspring.profiles.active=offline", "-jar", $m.Jar `
        -WorkingDirectory $dir -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $Destino "base\$($m.Pasta).log") `
        -RedirectStandardError (Join-Path $Destino "base\$($m.Pasta).err.log")
    $ids += $p.Id
    Write-Host "$($m.Pasta): iniciando na porta $($m.Porta) (PID $($p.Id))"
}
$ids | Set-Content $Pids
Write-Host "Aguarde ~20s e confira: python3 motor/validacao_oficial.py --descobrir"
Write-Host "Para parar: calculadora-oficial\executar.ps1 -Parar"
