#!/bin/bash

# Script para executar exemplo completo de integração com a Calculadora RTC
# ============================================================================

# Determina diretório base (pai da pasta run/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
SCRIPTS_DIR="$BASE_DIR/scripts"
INPUT_DIR="$BASE_DIR/input"
OUTPUT_DIR="$BASE_DIR/output"

echo "================================================================"
echo "  Exemplo de Integração com Calculadora RTC"
echo "================================================================"
echo ""

# Verifica se Python está instalado
if ! command -v python3 &> /dev/null; then
    echo "ERRO: Python3 não encontrado. Por favor, instale o Python 3."
    exit 1
fi

# Verifica e instala dependências do requirements.txt
REQUIREMENTS_FILE="$BASE_DIR/requirements.txt"
if [ -f "$REQUIREMENTS_FILE" ]; then
    echo "Verificando dependências..."
    python3 -c "import requests" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "Instalando dependências do requirements.txt..."
        pip3 install -r "$REQUIREMENTS_FILE"
        if [ $? -ne 0 ]; then
            echo "ERRO: Falha ao instalar dependências."
            exit 1
        fi
        echo "Dependências instaladas com sucesso!"
    else
        echo "Dependências já instaladas."
    fi
else
    echo "AVISO: Arquivo requirements.txt não encontrado."
fi

# Verifica se arquivos de entrada existem
if [ ! -f "$INPUT_DIR/entrada-regime-geral.json" ]; then
    echo "ERRO: Arquivo de entrada não encontrado: $INPUT_DIR/entrada-regime-geral.json"
    exit 1
fi

if [ ! -f "$INPUT_DIR/nfe-sem-rtc.xml" ]; then
    echo "ERRO: Arquivo NFe não encontrado: $INPUT_DIR/nfe-sem-rtc.xml"
    exit 1
fi

# Cria pasta output se não existir
mkdir -p "$OUTPUT_DIR"

echo ""
echo "----------------------------------------------------------------"
echo "  Passo 1: Calcular tributos RTC"
echo "----------------------------------------------------------------"
python3 "$SCRIPTS_DIR/1-regime-geral.py"
if [ $? -ne 0 ]; then
    echo "ERRO: Falha no cálculo de tributos."
    exit 1
fi

echo ""
echo "----------------------------------------------------------------"
echo "  Passo 2: Gerar XML com grupos RTC"
echo "----------------------------------------------------------------"
python3 "$SCRIPTS_DIR/2-gerar-xml.py"
if [ $? -ne 0 ]; then
    echo "ERRO: Falha na geração do XML."
    exit 1
fi

echo ""
echo "----------------------------------------------------------------"
echo "  Passo 3: Validar XML gerado (opcional)"
echo "----------------------------------------------------------------"
python3 "$SCRIPTS_DIR/3-validar-grupo-xml.py"
# Continua mesmo se validação falhar (é opcional)

echo ""
echo "----------------------------------------------------------------"
echo "  Passo 4: Injetar grupos RTC na NFe"
echo "----------------------------------------------------------------"
python3 "$SCRIPTS_DIR/4-injetar-xml.py"
if [ $? -ne 0 ]; then
    echo "ERRO: Falha ao injetar XML."
    exit 1
fi

echo ""
echo "================================================================"
echo "SUCESSO: Processo concluído com sucesso!"
echo "================================================================"
echo ""
echo "Arquivos gerados em $OUTPUT_DIR:"
echo "  - saida-regime-geral.json   - Resultado do cálculo RTC"
echo "  - saida-gerar-xml.xml       - XML com grupos RTC"
echo "  - nfe-com-rtc.xml           - NFe final com RTC integrado"
echo ""
