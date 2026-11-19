# Changelog dos parâmetros da Reforma Tributária

## v2026.08.6 — 25/08/2026 (aprovado pelo usuário)

- **Lucro Presumido — majoração de 10% na presunção de IRPJ/CSLL sobre o
  excedente de R$ 5.000.000,00/ano** (LC 224/2025, sancionada 26/12/2025,
  + IN RFB 2.305/2025 e IN RFB 2.306/2026). Novos campos em `lucro_presumido`:
  `presuncao_irpj_majorada`, `presuncao_csll_majorada` (= percentual atual ×
  1,10) e `limite_anual_presuncao_padrao` (R$ 5.000.000,00). Vigência: **IRPJ
  desde 01/01/2026**; **CSLL desde 01/04/2026** (anterioridade nonagesimal,
  art. 195 §6º CF) — abaixo do limite, nenhuma mudança.
- **Simplificação declarada**: a norma opera em base **trimestral** (limite
  de R$ 1.250.000,00/trimestre, com transporte de saldo entre trimestres e
  ajuste no 4º trimestre); o motor (`motor/simulador.py`) trabalha em base
  **anual** e reutiliza a mesma carga do Presumido para todos os anos
  2026–2033 da matriz de transição (só IBS/CBS varia por ano) — por isso a
  majoração foi modelada como se já estivesse em regime de maturidade (IRPJ
  e CSLL majorados o ano inteiro), não a transição parcial real de 2026 (onde
  a CSLL só é majorada a partir do 2º trimestre). Isso é uma simplificação
  **favorável ao contribuinte real em 2026** (o modelo pode superestimar
  levemente a CSLL de 2026 frente ao que será apurado trimestre a trimestre).
  Documentado em `lucro_presumido.nota_majoracao_lc224` no JSON.
- **Mudança de código** (não cabia só no JSON): `motor/regime_atual.py`,
  `carga_presumido()` — passou a separar a receita anual em
  `normal = min(receita, limite)` e `excedente = max(0, receita - limite)`,
  aplicando os percentuais padrão sobre `normal` e os majorados sobre
  `excedente`. Compatível com parâmetros antigos (se `limite_anual_presuncao_padrao`
  ou as chaves `_majorada` não existirem, comporta-se exatamente como antes,
  sem majoração). Novos campos de rastreabilidade na `memoria` retornada:
  `receita_normal`, `receita_excedente_majorado`,
  `presuncao_irpj_aplicada_media`, `presuncao_csll_aplicada_media`.
- **RESSALVA JURÍDICA — controvérsia normativa ATIVA, não pacificada**: a
  1ª Vara Federal de Resende/RJ concedeu liminar em janeiro/2026 suspendendo
  a exigibilidade da majoração para o autor daquela ação específica, sob o
  argumento de que o Lucro Presumido não é benefício/gasto fiscal e a
  majoração tributaria "renda fictícia" (violação de isonomia pelo piso de
  R$ 5 milhões). A liminar tem efeito **inter partes** (não vale para todos
  os contribuintes) e pode ser revertida ou mantida por instâncias
  superiores. O simulador aplica a majoração como regra federal vigente por
  padrão — casos com decisão judicial própria devem ser avaliados
  separadamente pelo contador/advogado responsável. Fontes da controvérsia:
  conjur.com.br (2026-abr-21 e 2026-jul-15) e barbieriadvogados.com/lucro-presumido-liminar.
- Fontes primárias buscadas mas não confirmadas em planalto.gov.br/gov.br
  diretamente nesta sessão (paywall/indisponibilidade de acesso direto);
  conteúdo e datas confirmados de forma consistente em múltiplas fontes
  contábeis/jurídicas secundárias (contabeis.com.br, calculadoracontabil.com.br,
  nedereromano.com.br, gsga.com.br, omie.com.br, paulicon.com.br) — **recomenda-se
  confirmar o texto oficial da LC 224/2025 e da IN RFB 2.306/2026 diretamente
  em planalto.gov.br/gov.br/receitafederal antes de uso em cliente real com
  receita acima de R$ 5 milhões.**
- Validação de regressão: `exemplos/servicos_ti_teste.json` e
  `exemplos/comercio_teste.json` (ambos abaixo de R$ 5 milhões de receita) —
  sem mudança, como esperado. `empresas/edx-com-de-armarinhos/perfil_fiscal.json`
  (comércio, receita anualizada R$ 6.412.566,53) — IRPJ/CSLL do Presumido
  subiram ligeiramente sobre o excedente de R$ 1.412.566,53 acima de R$ 5 mi,
  como esperado.

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
