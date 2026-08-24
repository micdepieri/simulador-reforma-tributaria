# Integração ERP - Calculadora RTC

Scripts Python para integração com a Calculadora da Reforma Tributária (RTC).

## Estrutura de Arquivos

```
integracao-erp/
├── README.md                    # Este arquivo
├── scripts/                     # Scripts Python de integração
│   ├── 1-regime-geral.py       # Calcula tributos RTC
│   ├── 2-gerar-xml.py          # Gera XML com grupos RTC
│   ├── 3-validar-grupo-xml.py  # Valida XML gerado
│   └── 4-injetar-xml.py        # Injeta RTC na NFe
├── input/                       # Arquivos de entrada (fixos)
│   ├── entrada-regime-geral.json
│   └── nfe-sem-rtc.xml
├── output/                      # Arquivos gerados (saídas)
│   ├── saida-regime-geral.json
│   ├── saida-gerar-xml.xml
│   └── nfe-com-rtc.xml
└── run/                         # Scripts de execução
    ├── executar-exemplo.sh     # Linux/Mac
    └── executar-exemplo.bat    # Windows
```

## Como Usar

### Pré-requisitos

- Python 3.7 ou superior
- API da Calculadora RTC em `http://localhost:8080`

### Instalação

Instale as dependências necessárias:

```bash
pip install -r requirements.txt
```

Ou deixe o script de execução instalar automaticamente.

### Execução

#### Linux/Mac
```bash
cd run/
chmod +x executar-exemplo.sh
./executar-exemplo.sh
```

#### Windows
```cmd
cd run
executar-exemplo.bat
```

### O que acontece

O script executa automaticamente 4 passos:

1. **Calcular tributos** → Chama API com dados de `input/entrada-regime-geral.json`
2. **Gerar XML** → Cria XML com grupos RTC (IS, IBSCBS, totalizadores)
3. **Validar XML** → Verifica estrutura e regras (opcional)
4. **Injetar na NFe** → Adiciona grupos RTC no documento fiscal

Todos os arquivos gerados ficam em `output/`.


