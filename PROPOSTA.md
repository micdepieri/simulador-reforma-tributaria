# Simulador da Reforma Tributária — Proposta (v2, aprovada)

**Data:** 22/08/2026 · **Responsável:** Michael Pieri (Mappi Soluções em Contabilidade)

## Objetivo

Grupo de agentes/skills no Claude Code que, a partir dos documentos do cliente
(DRE, Balanço Patrimonial, folha de pagamento, extrato PGDAS-D, XMLs de notas de
entrada e saída), simula o impacto da Reforma Tributária (EC 132/2023 + LC 214/2025)
ano a ano durante a transição 2026–2033, comparando:

1. **Cenário atual** — carga efetiva hoje (Simples, Presumido ou Real)
2. **Simples Nacional na reforma** — Simples "cheio" × **Simples híbrido**
   (IBS/CBS recolhidos por fora do DAS para gerar crédito integral ao cliente B2B)
3. **Lucro Presumido × Lucro Real** sob CBS/IBS, ano a ano
4. **Efeito na cadeia** — créditos tomados nas entradas e crédito exigido pelos clientes

## Arquitetura

```
Skill orquestradora: /simulador-reforma
├── Agente 1 — ingestao-documentos      (Fase 2) DRE/BP/folha/PGDAS/XMLs → perfil fiscal JSON
├── Agente 2 — motor-regime-atual       (Fase 1) carga vigente: Simples / Presumido / Real
├── Agente 3 — motor-ibs-cbs            (Fase 1) LC 214/2025 + cronograma de transição
├── Agente 4 — simulador-simples        (Fase 2) cheio × híbrido + "teste do cliente" B2B
├── Agente 5 — comparativo-regimes      (Fase 3) matriz regimes × anos + sensibilidade ±20%
└── Agente 6 — relatorio-simulacao      (Fase 3) dashboard HTML (marca Mappi) + DOCX
```

Todos os cálculos rodam em **Python auditável** (`motor/`), com memória de cálculo em
CSV. Nenhum número é gerado "de cabeça".

## Escopo ampliado (v2) — pontos incorporados

### No motor de cálculo
1. **Fluxo de caixa / split payment** — módulo de impacto no capital de giro
   (antecipação do recolhimento na liquidação financeira). *(Fase 2)*
2. **Créditos de transição** — saldos credores de PIS/COFINS em 2027 e ICMS
   acumulado até 2032 (compensável em até 240 meses). *(Fase 2)*
3. **Benefícios fiscais atuais** — a carga vigente parte do **efetivo pago**
   (campo `aliquota_efetiva_icms` / `aliquota_efetiva_iss` no perfil fiscal),
   não da alíquota nominal. *(Fase 1 — já implementado)*
4. **Origem → destino** — perfil fiscal captura UF/município de destino;
   sinalização de exposição interestadual. *(Fase 2)*
5. **Regimes específicos e diferenciados da LC 214** — redutores parametrizados
   por categoria (0%, 30%, 60%, 100%) desde a Fase 1; regimes específicos
   (combustíveis, financeiro, imobiliário, hotelaria, transporte, ZFM) sinalizados
   e detalhados na Fase 2.
6. **Imposto Seletivo** — flag por enquadramento de CNAE/NCM. *(Fase 1 — sinalização)*
7. **Penalização da folha** — indicador folha/receita explícito no resultado
   (folha não gera crédito de IBS/CBS). *(Fase 1 — já implementado)*

### Camada de projeto
8. **Parâmetros versionados** — `parametros/parametros_reforma.json` único,
   com versão e data de vigência. Norma nova = atualizar um arquivo.
9. **Validação de qualidade dos dados** — checagens de coerência na ingestão
   (Fase 2); inconsistências listadas no relatório.
10. **LGPD e sigilo** — folha entra no perfil fiscal apenas como totais;
    nenhum dado nominal; dashboards só publicados após revisão.
11. **Disclaimer obrigatório** — premissas datadas + ressalva de responsabilidade
    técnica (CRC) em toda saída.

### Seções fixas do relatório (sem cálculo)
12. Repasse de preço e contratos vigentes (cláusula de revisão tributária)
13. Checklist de prontidão operacional (ERP, cadastros, obrigações acessórias 2026)
14. Cashback/B2C — menção qualitativa quando o mix for varejo

## Premissas do cenário-base (editáveis em `parametros_reforma.json`)

- Alíquota de referência IBS+CBS: **26,5%** (cenários 27,5% e 28,5%) —
  pendente de fixação definitiva; split CBS ≈ 8,8% / IBS ≈ 17,7%
- Cronograma: 2026 teste (0,9% + 0,1%, compensável) → 2027 CBS plena e extinção
  de PIS/COFINS, IPI zerado exceto ZFM → 2029–2032 ICMS/ISS em degraus
  (90/80/70/60%) com IBS proporcional (10/20/30/40%) → 2033 regime pleno
- Comparações normalizam a diferença de base "por dentro" × "por fora"

## Fases

| Fase | Conteúdo | Status |
|---|---|---|
| 1 | Parâmetros versionados + motor regime atual + motor IBS/CBS + perfil fiscal JSON + validação com empresas fictícias (serviço e comércio) | **Em construção** |
| 2 | Ingestão de documentos reais, simulador Simples cheio×híbrido com repartição por faixa, split payment/caixa, créditos de transição | Pendente |
| 3 | Comparativo completo com sensibilidade, relatório HTML (marca Mappi) + DOCX | Pendente |

## Ressalva técnica

Simulações baseadas na legislação vigente e em regulamentação **em andamento**;
alíquotas de referência pendentes de fixação. Resultados são estimativas de
planejamento e não substituem a análise do contador responsável (CRC).
