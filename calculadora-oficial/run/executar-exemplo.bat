@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM Script para executar exemplo completo de integração com a Calculadora RTC
REM ============================================================================

REM Determina diretório base (pai da pasta run\)
set "SCRIPT_DIR=%~dp0"
set "BASE_DIR=%SCRIPT_DIR%.."
set "SCRIPTS_DIR=%BASE_DIR%\scripts"
set "INPUT_DIR=%BASE_DIR%\input"
set "OUTPUT_DIR=%BASE_DIR%\output"

echo ================================================================
echo   Exemplo de Integração com Calculadora RTC
echo ================================================================
echo.

REM Verifica se Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python não encontrado. Por favor, instale o Python 3.
    pause
    exit /b 1
)

REM Verifica e instala dependências do requirements.txt
set "REQUIREMENTS_FILE=%BASE_DIR%\requirements.txt"
if exist "%REQUIREMENTS_FILE%" (
    echo Verificando dependências...
    python -c "import requests" >nul 2>&1
    if errorlevel 1 (
        echo Instalando dependências do requirements.txt...
        pip install -r "%REQUIREMENTS_FILE%"
        if errorlevel 1 (
            echo ERRO: Falha ao instalar dependências.
            pause
            exit /b 1
        )
        echo Dependências instaladas com sucesso!
    ) else (
        echo Dependências já instaladas.
    )
) else (
    echo AVISO: Arquivo requirements.txt não encontrado.
)

REM Verifica se arquivos de entrada existem
if not exist "%INPUT_DIR%\entrada-regime-geral.json" (
    echo ERRO: Arquivo de entrada não encontrado: %INPUT_DIR%\entrada-regime-geral.json
    pause
    exit /b 1
)

if not exist "%INPUT_DIR%\nfe-sem-rtc.xml" (
    echo ERRO: Arquivo NFe não encontrado: %INPUT_DIR%\nfe-sem-rtc.xml
    pause
    exit /b 1
)

REM Cria pasta output se não existir
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo.
echo ----------------------------------------------------------------
echo   Passo 1: Calcular tributos RTC
echo ----------------------------------------------------------------
python "%SCRIPTS_DIR%\1-regime-geral.py"
if errorlevel 1 (
    echo ERRO: Falha no cálculo de tributos.
    pause
    exit /b 1
)

echo.
echo ----------------------------------------------------------------
echo   Passo 2: Gerar XML com grupos RTC
echo ----------------------------------------------------------------
python "%SCRIPTS_DIR%\2-gerar-xml.py"
if errorlevel 1 (
    echo ERRO: Falha na geração do XML.
    pause
    exit /b 1
)

echo.
echo ----------------------------------------------------------------
echo   Passo 3: Validar XML gerado (opcional)
echo ----------------------------------------------------------------
python "%SCRIPTS_DIR%\3-validar-grupo-xml.py"
REM Continua mesmo se validação falhar (é opcional)

echo.
echo ----------------------------------------------------------------
echo   Passo 4: Injetar grupos RTC na NFe
echo ----------------------------------------------------------------
python "%SCRIPTS_DIR%\4-injetar-xml.py"
if errorlevel 1 (
    echo ERRO: Falha ao injetar XML.
    pause
    exit /b 1
)

echo.
echo ================================================================
echo SUCESSO: Processo concluído com sucesso!
echo ================================================================
echo.
echo Arquivos gerados em %OUTPUT_DIR%:
echo   - saida-regime-geral.json   - Resultado do cálculo RTC
echo   - saida-gerar-xml.xml       - XML com grupos RTC
echo   - nfe-com-rtc.xml           - NFe final com RTC integrado
echo.
pause
