---
name: simulador-reforma
description: Simula o impacto da Reforma Tributária (EC 132/2023 + LC 214/2025) para uma empresa durante a transição 2026-2033, comparando Simples cheio, Simples híbrido, Lucro Presumido e Lucro Real. Use quando o usuário pedir simulação da reforma, comparativo IBS/CBS, impacto da transição, ou análise Simples × Presumido × Real sob a reforma.
---

# Simulador da Reforma Tributária

## Fluxo

1. **Perfil fiscal.** Se o usuário forneceu documentos (DRE, BP, folha, PGDAS-D, XMLs),
   extraia os dados e monte um JSON no formato de `exemplos/servicos_ti_teste.json`
   (campos definidos em `motor/perfil_fiscal.py`). Se faltar dado essencial, pergunte
   apenas o mínimo: receita anual, atividade, regime atual, anexo (se Simples),
   folha anual, compras creditáveis, mix B2B, alíquotas EFETIVAS de ICMS/ISS pagas hoje.
   **LGPD:** folha entra apenas como total anual — nunca dados nominais.

2. **Classificação LC 214 — pela base oficial da Receita.** Quando houver itens
   identificáveis (XMLs de saída, catálogo de produtos/serviços), delegue ao agente
   `classificacao-oficial`: ele usa `motor/base_oficial.py` (banco normativo da
   Calculadora de Tributos, montado localmente a partir do GitHub da Receita) e grava no
   perfil o `mix_redutores` item a item, com a versão do banco. Reduções que dependem do
   texto de um anexo da LC 214 só entram no mix depois de conferidas — até lá, integral.
   Sem itens, determine `categoria_redutor` (padrao | profissoes_regulamentadas |
   reducao_60 | cesta_basica) pelo CNAE/atividade. Em ambos os casos sinalize
   `regime_especifico` e `sujeito_imposto_seletivo` (listas em
   `parametros/parametros_reforma.json`).

3. **Simulação.** Salve o perfil em `exemplos/` (ou pasta do cliente) e rode:
   ```
   python3 motor/simulador.py <perfil.json> base
   python3 motor/simulador.py <perfil.json> conservador
   python3 motor/simulador.py <perfil.json> pessimista
   ```
   Saídas em `saidas/<empresa>/`: matriz CSV + resumo Markdown.

4. **Validação oficial (opcional, recomendada quando as APIs estiverem no ar).**
   A Calculadora de Tributos é código aberto (Release 15): instale com
   `calculadora-oficial/instalar-github.ps1` (ou `.sh`) e suba com `executar.ps1`
   (regime regular em :8080, Simples em :8082). Então:
   ```
   python3 motor/validacao_oficial.py <perfil.json> --itens <itens.json>
   python3 motor/validacao_oficial.py <perfil.json> --simples        # optantes do Simples
   ```
   Itens sem `cst`/`cclasstrib` são classificados pela base oficial antes do envio.
   A partir de 2027 a API exige `aliquotasNominais` — enviamos as do cenário local,
   então a validação confere a CLASSIFICAÇÃO (rejeição REG-011, redução aplicada),
   não a alíquota. Item rejeitado ou divergente = corrija o perfil ANTES de entregar.
   No modo `--simples`, confere o IBS/CBS destacado na nota do optante (o crédito do
   cliente B2B) com os percentuais que o motor estima — a alíquota efetiva em si é do
   PGDAS-D e a Calculadora não a calcula.
   `--dados-abertos` lista as alíquotas de referência oficiais (funciona sem a API,
   pelo banco local): desde a V0053 **não existe alíquota oficial para 2027+**.
   Se as APIs não estiverem no ar, siga sem esta etapa (nunca bloqueia) e registre
   no relatório que a validação contra a API oficial não foi feita.

5. **Entrega.** Apresente: melhor regime por ano, curva da carga na transição,
   indicadores estruturais (folha/receita, crédito B2B), o **repasse de preço
   necessário** por ano/regime (`motor/precificacao.py` — ver seção própria no
   resumo e no relatório HTML) e SEMPRE as ressalvas (alíquota pendente de
   fixação — nenhum cenário é "oficial": a Receita retirou as alíquotas pós-2026 do
   banco da Calculadora —, versão dos parâmetros e do banco oficial usadas, itens
   com redução ainda a confirmar, repasse é modelo a volume constante sem
   elasticidade de demanda, análise final é do contador CRC). Inclua as seções
   qualitativas: contratos vigentes (cláusula de revisão tributária), checklist de
   prontidão operacional, cashback/B2C se varejo.

## Regras invioláveis

- **Nunca calcule tributos "de cabeça"** — todo número sai do motor Python.
- **Nenhum parâmetro hardcoded** — alíquotas/regras só em `parametros/parametros_reforma.json`.
  Se o usuário relatar norma nova, use o agente `atualizacao-normativa` para propor o
  diff do JSON, atualize `parametros/CHANGELOG.md` e incremente `versao`.
- Toda saída cita a versão dos parâmetros usada.
- Se a empresa tiver `regime_especifico` da LC 214, avise que o cálculo detalhado
  do setor está na Fase 2 e trate o resultado como aproximação.
