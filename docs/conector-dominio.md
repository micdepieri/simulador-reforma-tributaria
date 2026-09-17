# Conector do Domínio ERP (opcional)

O simulador funciona **sem** este conector: o caminho padrão é o `/iniciar`,
que monta o perfil fiscal a partir dos documentos da empresa (DRE, balanço,
folha, PGDAS-D, XMLs).

Este documento é para quem usa o **Domínio ERP (Thomson Reuters)** e quer
puxar os dados direto do banco, poupando a coleta manual da parte que o
sistema já tem escriturada.

## O que o conector entrega (e o que não entrega)

| Campo do perfil fiscal | Vem do Domínio? |
|---|---|
| `nome`, `uf` | sim — `bethadba.geempre` |
| `regime_atual` | sim — deduzido dos impostos apurados |
| `receita_bruta_anual`, `rbt12` | sim — saídas + serviços da janela, anualizados |
| `folha_anual` | sim — proventos por competência |
| `aliquota_efetiva_icms`, `aliquota_efetiva_iss` | sim — devido ÷ receita da janela |
| `compras_creditaveis_anual` | sim — entradas classificadas por CFOP |
| `atividade` | parcial — comércio × serviços pela receita; indústria precisa de confirmação |
| `anexo_simples` | parcial — presumido pela atividade e pelo fator R; confirmar no PGDAS-D |
| `cnae_principal` | **não** — cadastro/CNPJ |
| `cmv_anual`, `despesas_operacionais_anual` | **não** — DRE |
| `mix_b2b` | **não** — XMLs de saída |

Os dois caminhos se somam: o Domínio resolve cadastro, apuração e compras, os
documentos resolvem a estrutura de custo e o perfil de clientes.

## Crédito de IBS/CBS a partir das entradas

As notas de entrada saem agrupadas por **CFOP** (`efentradas.codi_nat`, descrito
em `efnatureza`) e por **acumulador** (a classificação que o próprio escritório
deu à operação na escrita fiscal).

A régua de elegibilidade é a da **LC 214, não a do ICMS**. A não cumulatividade
plena dá crédito sobre toda aquisição onerosa usada na atividade, então entram
coisas que no ICMS não geram crédito (ou geram parcelado pelo CIAP):

- **entram**: compras para revenda e industrialização, inclusive com ST; energia,
  água, gás e comunicação; serviços de transporte tomados; serviços sob ISS
  (CFOP 933); **uso e consumo** e **ativo imobilizado**;
- **ficam de fora**: devolução de venda (é estorno de saída, não compra),
  transferência entre estabelecimentos da mesma empresa, remessas e retornos
  (comodato, consignação, industrialização por encomenda, demonstração);
- **vão para revisão**: CFOPs ambíguos entre compra e devolução em ST
  (410, 411, 414, 415) e qualquer CFOP fora da tabela — o conector nunca
  os inclui sozinho, lista para o contador decidir.

Três coisas que o CFOP **não** resolve, e que aparecem como lacuna:

1. **Fornecedor optante pelo Simples** — o crédito do adquirente é limitado ao
   que o fornecedor recolheu, não à alíquota cheia. O valor extraído assume
   crédito integral e é, nessa medida, otimista. Para refinar, use o agente
   `levantamento-creditos-ibs-cbs`.
2. **Uso pessoal de sócios e administradores** (art. 57) — não gera crédito e
   nenhum CFOP o distingue. É para isso que serve a tabela por acumulador.
3. **ICMS-ST pago na entrada** — não vira crédito de IBS/CBS; sai destacado
   para avaliar o estoque com ST na virada.

A partir das competências de 2026 o Domínio já escritura IBS e CBS por nota
(`EFENTRADAS_IVA_IBS` e `EFENTRADAS_IVA_CBS`, com CST e cClassTrib). Quando
houver movimento nessas tabelas, esse é o crédito **real** — o conector o traz
junto, para aferir a estimativa por CFOP em vez de confiar só nela.

Para classificar produtos por NCM (cesta básica, medicamentos, tratamento
diferenciado), o catálogo da empresa está em `efprodutos` (`cncm_pdi` para NCM,
`CODIGO_NBS` para serviços) — é a entrada do agente `classificacao-ncm-ibs-cbs`.

## Janela de análise

O conector **nunca** varre o banco inteiro. Toda extração declara uma janela de
competências, com padrão de **6 meses** — recente o bastante para refletir a
operação atual, leve o bastante para não puxar anos de movimento.

Como o perfil fiscal é anual por contrato, uma janela menor que 12 meses é
**anualizada por regra de três**. Isso é projeção, não apuração: sazonalidade
não é modelada. O conector registra o fator aplicado nas `observacoes` do perfil
e emite uma lacuna explícita. Para negócio sazonal (comércio de fim de ano,
turismo, agro, escola), use `--meses 12`.

No Simples isso importa duas vezes: o `rbt12` projetado define faixa e
sublimite. Confira contra o RBT12 real do extrato do PGDAS-D antes de simular.

## Configuração

O acesso ao banco é feito por um **servidor MCP externo**, que não faz parte
deste repositório — assim nenhuma credencial de banco mora no projeto.

### 1. DSN ODBC

Crie um DSN ODBC apontando para a base do Domínio (SQL Anywhere/Sybase), com
usuário **somente leitura**. No Windows: *Administrador de Fonte de Dados ODBC
(64 bits)* → *DSN de Sistema* → *Adicionar* → driver do SQL Anywhere. Anote o
nome do DSN.

Use um usuário de banco sem permissão de escrita. O conector só faz `SELECT`,
mas a garantia real está na permissão, não na boa intenção do código.

### 2. Servidor MCP

Um servidor MCP mínimo, em Python, expondo três ferramentas de leitura
(`executar_sql`, `listar_tabelas`, `descrever_tabela`) sobre `pyodbc`:

```python
import json
import pyodbc
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Sybase ODBC")
DSN_NAME = "SEU_DSN"          # <- o DSN criado no passo 1


def get_connection():
    return pyodbc.connect(f"DSN={DSN_NAME}", autocommit=True)


@mcp.tool()
def executar_sql(query: str) -> str:
    """Executa uma query SQL no banco Sybase e retorna os resultados."""
    if not query.lstrip().upper().startswith("SELECT"):
        return "Erro: este conector aceita apenas SELECT."
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        if cursor.description is None:
            return "Query executada sem retorno de dados."
        colunas = [c[0] for c in cursor.description]
        linhas = cursor.fetchmany(200)
        return json.dumps([dict(zip(colunas, l)) for l in linhas],
                          default=str, ensure_ascii=False, indent=2)
    finally:
        conn.close()


@mcp.tool()
def listar_tabelas() -> str:
    """Lista as tabelas disponíveis no banco."""
    conn = get_connection()
    try:
        return "\n".join(r.table_name for r in conn.cursor().tables(tableType="TABLE"))
    finally:
        conn.close()


@mcp.tool()
def descrever_tabela(nome_tabela: str) -> str:
    """Retorna as colunas e tipos de uma tabela."""
    conn = get_connection()
    try:
        colunas = conn.cursor().columns(table=nome_tabela)
        return json.dumps([{"coluna": c.column_name, "tipo": c.type_name,
                            "tamanho": c.column_size} for c in colunas],
                          ensure_ascii=False, indent=2)
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

Registre-o com o nome `sybase-cloud` (é o nome que o agente procura):

```bash
claude mcp add sybase-cloud -- python /caminho/para/servidor.py
```

### 3. Conferir

Peça ao Claude: *"liste as tabelas do Domínio"*. Se vier a lista com tabelas
`bethadba.*`, está pronto.

## Uso

Com o MCP ativo, o `/iniciar` pergunta se você quer puxar do Domínio e delega
ao agente `conector-dominio`, que combina a janela, identifica a empresa,
extrai e monta o perfil. Também dá para chamar direto: *"monte o perfil da
<empresa> pelo Domínio, últimos 6 meses"*.

Os comandos por trás, se quiser rodar à mão:

```bash
python3 motor/conector_dominio.py --queries <codi_emp> --meses 6
```

```bash
python3 motor/conector_dominio.py --extracao empresas/<slug>/extracao_dominio.json --saida empresas/<slug>/perfil_fiscal.json
```

Quem tem o ODBC na própria máquina e `pyodbc` instalado pode pular o MCP:

```bash
python3 motor/conector_dominio.py --dsn SEU_DSN --empresa <codi_emp> --meses 6 --saida-extracao empresas/<slug>/extracao_dominio.json
```

## Convenções do banco Domínio

Valem para qualquer query que você acrescente:

- owner `bethadba.` em todas as tabelas;
- `SELECT TOP N`, nunca `LIMIT` (é Sybase);
- `JOIN bethadba.geimposto` sempre com `AND i.codi_emp = 1`;
- `codi_emp` 1 e 50010 são registros internos do escritório — excluir;
- competências no formato `'YYYY-MM-01'`;
- sempre filtre por `codi_emp` primeiro, ou a query fica lenta.

Identificação do regime: `codi_imp` 44 = Simples, 64 = MEI (fora do escopo do
motor), 7/6 = Presumido, registro em `bethadba.lrcalculo` = Lucro Real.

Colunas que costumam ser escritas errado: `efservicos` usa `vcon_ser` e
`dser_ser`; `efsaidas` usa `vcon_sai` e `dsai_sai`; `lrcalculo` usa
`COMPETENCIA`.

## LGPD

`empresas/` e `saidas/` estão no `.gitignore` — extrações e perfis de clientes
reais nunca sobem ao repositório. Da folha, o conector puxa apenas o **total de
proventos por competência**, nunca dados individuais de empregados.
