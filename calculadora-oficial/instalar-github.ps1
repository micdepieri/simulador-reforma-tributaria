# Instala a Calculadora de Tributos da Receita Federal a partir do codigo aberto no GitHub
# (Release 15+): modulo do regime regular (porta 8080) e do Simples Nacional (porta 8082).
#
# Requisitos: Git, Java 21+ e Python 3 (o Maven vem pelo wrapper mvnw, que precisa de internet
# na primeira execucao). Uso, a partir da raiz do projeto:
#     powershell -ExecutionPolicy Bypass -File calculadora-oficial\instalar-github.ps1
#
# O que faz:
#   1. clona (ou atualiza) os dois repositorios oficiais em calculadora-oficial\
#   2. monta o banco normativo com motor\base_oficial.py (Python puro, sem Flyway)
#   3. copia o banco para calculadora\db\ de cada modulo e compila os JARs (sem testes)
# Rode de novo sempre que 'python3 motor/base_oficial.py novidades' avisar migracao nova.

$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $PSScriptRoot
$Destino = Join-Path $Raiz "calculadora-oficial"
$Py = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }

foreach ($cmd in @("git", "java")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "Comando '$cmd' nao encontrado no PATH." }
}

$Modulos = @(
    @{ Pasta = "regime-regular";   Url = "https://github.com/ReceitaFederal/calculadora-rtc-regime-regular.git" },
    @{ Pasta = "simples-nacional"; Url = "https://github.com/ReceitaFederal/calculadora-rtc-simples-nacional.git" }
)

foreach ($m in $Modulos) {
    $dir = Join-Path $Destino $m.Pasta
    if (Test-Path (Join-Path $dir ".git")) {
        Write-Host "Atualizando $($m.Pasta)..."
        git -C $dir -c core.longpaths=true pull --ff-only
    } else {
        Write-Host "Clonando $($m.Pasta)..."
        git -c core.longpaths=true clone --depth 1 $m.Url $dir
    }
    if ($LASTEXITCODE -ne 0) { throw "Falha no git para $($m.Pasta)." }
}

Write-Host "Montando o banco normativo oficial (a partir dos scripts SQL do regime regular)..."
& $Py (Join-Path $Raiz "motor\base_oficial.py") montar --fonte (Join-Path $Destino "regime-regular\flyway\sql")
if ($LASTEXITCODE -ne 0) { throw "Falha ao montar o banco oficial." }
$Banco = Join-Path $Destino "base\calculadora-pro.db"

foreach ($m in $Modulos) {
    $dir = Join-Path $Destino $m.Pasta
    New-Item -ItemType Directory -Force (Join-Path $dir "calculadora\db") | Out-Null
    Copy-Item $Banco (Join-Path $dir "calculadora\db\calculadora-pro.db") -Force
    Write-Host "Compilando $($m.Pasta) (primeira vez baixa o Maven; alguns minutos)..."
    Push-Location $dir
    try {
        & .\mvnw.cmd -q -B clean package -DskipTests
        if ($LASTEXITCODE -ne 0) { throw "Falha na compilacao de $($m.Pasta)." }
    } finally { Pop-Location }
}

Write-Host ""
Write-Host "Pronto. Para subir as APIs: calculadora-oficial\executar.ps1"
Write-Host "Depois confira: python3 motor/validacao_oficial.py --descobrir"
