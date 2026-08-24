# Changelog dos parâmetros da Reforma Tributária

## v2026.08.5 — 23/08/2026 (aprovado pelo usuário)

- **Cenário base: 26,5% → 27,0%** (CBS 8,5% + IBS 18,5%), espelhando a
  referência oficial embarcada no banco V0042 (07/07/2026) da Calculadora de
  Tributos da RFB, extraída via dados abertos (`--dados-abertos`).
  Com a redução de 0,1 p.p. na CBS em 2027-2028, o modelo reproduz exatamente
  a CBS oficial de 8,4% nesses anos.
- Novo cenário `otimista` (26,5% — antiga base); `conservador` (27,5%) e
  `pessimista` (28,5%) reescalonados na proporção do split oficial.
- Validação pós-mudança: regressão nos 2 perfis de teste × cenários + item de
  regra geral contra a Calculadora oficial.

## v2026.08.4b — 23/08/2026 (Fase 4 — cobertura da API oficial)

- `calculadora_oficial`: corrigido `endpoint_swagger` (`/api/api-docs`), novos
  `endpoint_status` (`/api/versao/status` — health + versões app/banco e flag
  de atualização frente ao remoto) e `endpoint_dados_abertos`.
- `motor/validacao_oficial.py --dados-abertos`: extrai as alíquotas de
  referência OFICIAIS embarcadas no banco da Calculadora (CBS União, IBS UF,
  IBS município) para 2026–2033 e salva espelho para o agente
  atualizacao-normativa. Nunca altera parâmetros automaticamente.
- Espelho de validação agora carimba versão do app/banco da Calculadora e a
  versão local de parâmetros (rastreabilidade total).
- ACHADO (banco V0042, 07/07/2026): referência oficial 2033 = CBS 8,5% +
  IBS 18,5% (UF 16,0% + municipal 2,5%) = 27,0%, vs cenário base local de
  26,5%. Estrutura do cronograma local CONFIRMADA (degraus IBS 10/20/30/40%
  batem exatamente). Ajuste de cenário pendente de aprovação.

## v2026.08.4 — 22/08/2026 (Fase 4)

- Novo bloco `calculadora_oficial`: integração com o **módulo offline** da
  Calculadora de Tributos da Receita Federal (portal do piloto
  piloto-cbs.tributos.gov.br). Não há API pública online (FAQ do Piloto v1.4);
  o módulo roda localmente com API REST + Swagger embutido.
- `motor/validacao_oficial.py`: descoberta de endpoints via Swagger
  (`--descobrir`) e validação cruzada por item (NCM/NBS, data do fato gerador,
  local, CST × cClassTrib, base de cálculo) — compara a alíquota efetiva
  oficial com a do motor e gera espelho de divergências por empresa.
- Papel arquitetural fixado: a calculadora oficial **valida e abastece
  parâmetros; nunca calcula por dentro do motor** — simulações permanecem
  reproduzíveis pela versão deste JSON.
- Ressalva: tratamento do Simples Nacional ainda em desenvolvimento na
  Calculadora (FAQ 4.2) — validação cobre o regime regular.

## v2026.08.3 — 22/08/2026 (Fase 3)

- Novo bloco `regimes_especificos_detalhe`: reduções próprias aplicáveis no
  cálculo — hotelaria/bares/restaurantes (−40%), transporte coletivo (−40%),
  locação imobiliária (−70%), alienação imobiliária (−50%) — **CONFERIR redação
  final da LC 214 antes de uso em cliente real**. Prevalecem sobre a categoria
  geral de redutor quando `regime_especifico` estiver preenchido no perfil.
- Regimes com alíquota/base própria (combustíveis, financeiro, planos de saúde,
  ZFM, apostas) seguem apenas sinalizados (aproximação pela regra geral).

## v2026.08.2 — 22/08/2026 (Fase 2)

- Repartição do DAS **por faixa** (`reparticao_faixas`) nos Anexos I–V, conforme
  LC 123 — **CONFERIR contra o texto legal antes de uso em cliente real**;
  na 6ª faixa ICMS/ISS é recolhido por fora do DAS.
- Novo bloco `financeiro`: taxa de capital de giro (15% a.a.) e float médio de
  recolhimento (25 dias) para o modelo de split payment.
- Nenhuma alteração normativa de alíquotas/cronograma nesta versão.

Toda alteração em `parametros_reforma.json` é registrada aqui pelo agente
`atualizacao-normativa`, com norma de origem e o que mudou.

## v2026.08.1 — 22/08/2026 (versão inicial)

- Cenários de alíquota de referência: 26,5% (base), 27,5%, 28,5% — estimativas;
  alíquota definitiva pendente de resolução do Senado.
- Cronograma de transição 2026–2033 conforme EC 132/2023 / LC 214/2025.
- Redutores LC 214: 0% / 30% (profissões regulamentadas) / 60% / 100% (cesta básica).
- Tabelas Simples Nacional Anexos I–V (LC 123) com repartição média de tributos
  sobre consumo por anexo (referência 3ª faixa) — **a refinar por faixa na Fase 2**.
- Parâmetros de Lucro Presumido e Lucro Real (IRPJ/CSLL/PIS/COFINS).
