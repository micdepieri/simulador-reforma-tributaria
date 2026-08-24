# Empresas

Cada empresa real analisada tem sua própria pasta aqui, com os documentos-fonte
e o perfil fiscal gerado a partir deles. **Esta pasta contém dados reais de
clientes e não é versionada** (ver `.gitignore`) — apenas este README e o
modelo em `_modelo/` sobem ao repositório.

## Como criar uma empresa nova

1. Copie `_modelo/` para uma pasta com o nome da empresa (slug, sem espaços/acentos):
   ```bash
   cp -r empresas/_modelo empresas/nome-da-empresa
   ```
2. **Não precisa organizar nada.** Jogue todos os arquivos recebidos do
   cliente (DRE, balanço, folha, PGDAS-D, XMLs) direto em
   `empresas/nome-da-empresa/novos/`, sem se preocupar em separar por tipo —
   é assim que o cliente manda na prática.
3. No Claude Code, peça a análise (ex.: *"classifique os documentos e monte o
   perfil fiscal da empresa em empresas/nome-da-empresa"*). O agente
   `ingestao-documentos`:
   - roda `motor/classificador_documentos.py` para identificar cada arquivo
     pelo nome (PDF/Excel) ou pelo conteúdo (XML — NF-e/NFS-e, decide
     entrada/saída pelo CNPJ) e move para a subpasta certa dentro de
     `documentos/` (veja estrutura abaixo);
   - o que não for reconhecido automaticamente fica listado em
     `documentos/_relatorio_classificacao.json` (`pendentes_revisao`) para
     revisão manual do conteúdo;
   - extrai os dados de cada documento já classificado e monta o perfil fiscal.
4. O skill `simulador-reforma` roda a simulação a partir do perfil fiscal.
   O perfil é salvo em `empresas/nome-da-empresa/perfil_fiscal.json` e as
   saídas (matriz CSV + resumo Markdown) em `empresas/nome-da-empresa/saidas/`.

Se preferir organizar manualmente em vez de usar `novos/`, pode colocar os
documentos direto nas subpastas de `documentos/`:
- `dre/` — Demonstração do Resultado (PDF/Excel), receita bruta, CMV, despesas anuais.
- `balanco_patrimonial/` — imobilizado, estoques, saldos credores de tributos.
- `folha/` — total bruto anual da folha (LGPD: nunca dados nominais).
- `pgdas/` — extratos do PGDAS-D (se optante do Simples), para validar a alíquota efetiva.
- `xmls/entrada/` e `xmls/saida/` — XMLs de NF-e/NFS-e, separados por direção.

## Estrutura de cada empresa

```
empresas/nome-da-empresa/
  novos/                  ← jogue aqui os arquivos recebidos do cliente, sem organizar
  documentos/
    _relatorio_classificacao.json  ← gerado pelo classificador (o que foi movido/pendente)
    dre/
    balanco_patrimonial/
    folha/
    pgdas/
    xmls/
      entrada/
      saida/
  perfil_fiscal.json     ← gerado pelo agente ingestao-documentos
  saidas/                ← matriz CSV + resumo Markdown da simulação
```

## LGPD

- Nunca coloque dados nominais de funcionários — apenas o total bruto anual da folha.
- Toda a pasta `empresas/` (exceto `_modelo/` e este README) é ignorada pelo git.
