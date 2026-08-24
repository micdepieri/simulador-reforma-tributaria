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

2. **Classificação LC 214.** Determine `categoria_redutor` (padrao | profissoes_regulamentadas
   | reducao_60 | cesta_basica) pelo CNAE/atividade, e sinalize `regime_especifico` e
   `sujeito_imposto_seletivo` quando aplicável (listas em `parametros/parametros_reforma.json`).

3. **Simulação.** Salve o perfil em `exemplos/` (ou pasta do cliente) e rode:
   ```
   python3 motor/simulador.py <perfil.json> base
   python3 motor/simulador.py <perfil.json> conservador
   python3 motor/simulador.py <perfil.json> pessimista
   ```
   Saídas em `saidas/<empresa>/`: matriz CSV + resumo Markdown.

4. **Validação oficial (opcional, recomendada quando o módulo estiver instalado).**
   Se o módulo offline da Calculadora de Tributos da Receita estiver rodando
   localmente (`calculadora_oficial.habilitada: true` nos parâmetros), monte um
   `itens.json` com os NCMs/NBS principais do cliente (a partir de
   `saidas/resumo_xmls.json`) e rode:
   ```
   python3 motor/validacao_oficial.py <perfil.json> --itens <itens.json>
   ```
   Divergências entre o motor e a calculadora oficial indicam erro de
   classificação de `categoria_redutor` — corrija o perfil ANTES de entregar.
   Comandos auxiliares: `--dados-abertos` (alíquotas de referência oficiais do
   banco embarcado, para conferir os cenários locais) e `--descobrir` (lista os
   ~40 endpoints da API local, incluindo consultas de cClassTrib, NCM/NBS
   aplicável e NFS-e). O módulo sobe com `./calculadora-oficial/iniciar-macos.sh`.
   Se o módulo não estiver instalado, siga sem esta etapa (nunca bloqueia) e
   registre no relatório que a classificação de redutores não foi validada
   contra a fonte oficial. Ressalva: Simples Nacional ainda em desenvolvimento
   na Calculadora — validação vale para o regime regular.

5. **Entrega.** Apresente: melhor regime por ano, curva da carga na transição,
   indicadores estruturais (folha/receita, crédito B2B), e SEMPRE as ressalvas
   (alíquota pendente de fixação, versão dos parâmetros usada, análise final é do
   contador CRC). Inclua as seções qualitativas: contratos vigentes, checklist de
   prontidão operacional, cashback/B2C se varejo.

## Regras invioláveis

- **Nunca calcule tributos "de cabeça"** — todo número sai do motor Python.
- **Nenhum parâmetro hardcoded** — alíquotas/regras só em `parametros/parametros_reforma.json`.
  Se o usuário relatar norma nova, use o agente `atualizacao-normativa` para propor o
  diff do JSON, atualize `parametros/CHANGELOG.md` e incremente `versao`.
- Toda saída cita a versão dos parâmetros usada.
- Se a empresa tiver `regime_especifico` da LC 214, avise que o cálculo detalhado
  do setor está na Fase 2 e trate o resultado como aproximação.
