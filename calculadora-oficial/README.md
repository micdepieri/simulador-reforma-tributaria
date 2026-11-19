# Calculadora de Tributos oficial (Receita Federal)

Desde a **Release 15 (out/2026)** a Calculadora é código aberto no GitHub da Receita:

| Módulo | Repositório | Porta local |
|---|---|---|
| Regime regular (CBS/IBS/IS) — contém o banco normativo em SQL | [calculadora-rtc-regime-regular](https://github.com/ReceitaFederal/calculadora-rtc-regime-regular) | 8080 |
| Simples Nacional | [calculadora-rtc-simples-nacional](https://github.com/ReceitaFederal/calculadora-rtc-simples-nacional) | 8082 |

Há **dois níveis de uso** no simulador:

1. **Banco oficial, sem instalar nada além do Python** — o que o simulador usa no
   dia a dia para classificar itens (NCM/NBS/LC 116 → cClassTrib → redução):
   ```bash
   python3 motor/base_oficial.py montar        # baixa os scripts SQL do GitHub e monta o SQLite
   python3 motor/base_oficial.py novidades     # a Receita publicou migração nova?
   ```
   O banco fica em `calculadora-oficial/base/` (fora do git; regenerável).

2. **APIs oficiais rodando localmente** — opcional, para a validação cruzada
   (`motor/validacao_oficial.py`). Requer Git, Java 21+ e Python 3:
   ```powershell
   powershell -ExecutionPolicy Bypass -File calculadora-oficial\instalar-github.ps1
   powershell -ExecutionPolicy Bypass -File calculadora-oficial\executar.ps1
   ```
   No Linux/macOS: `./calculadora-oficial/instalar-github.sh` e `./calculadora-oficial/executar.sh`
   (`--parar` / `-Parar` para encerrar). Os fontes clonados ficam em
   `calculadora-oficial/regime-regular/` e `simples-nacional/` (fora do git).

> Desde a migração V0053 o banco oficial não tem alíquota de referência de CBS/IBS
> para 2027+ (não definida em lei): a API exige `aliquotasNominais` e responde
> `CALCULO_SIMULADO`. O simulador envia as alíquotas do cenário local — a validação
> confere a classificação, não a alíquota.

---

## Pacote antigo do portal piloto (V0042 – 1.3.0) — exemplos de integração ERP

Superado pelo código aberto acima; mantido como referência dos scripts de exemplo.
Os scripts `iniciar-macos.sh`, `parar-macos.sh` e as pastas `linux/`/`windows/` são
desse pacote (Docker).

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


