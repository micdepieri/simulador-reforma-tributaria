# Simulador da Reforma Tributária — Mappi

Simula o impacto da Reforma Tributária (EC 132/2023 + LC 214/2025) para empresas
durante a transição 2026–2033, comparando **Simples cheio × Simples híbrido ×
Lucro Presumido × Lucro Real**, a partir de DRE, BP, folha, PGDAS-D e XMLs.

Proposta completa e escopo: [PROPOSTA.md](PROPOSTA.md)

## Como usar

Para uma empresa nova, no Claude Code digite **/iniciar** — ele entrevista você
(nome da empresa, documentos), cria a pasta em `empresas/`, classifica os
documentos e roda a análise completa, avisando sobre inconsistências ou dados
faltantes ao longo do processo.

Se já tiver o perfil fiscal montado, invoque a skill **/simulador-reforma**
diretamente (ela roda o motor a partir do perfil). Ou manualmente:

```bash
python3 motor/simulador.py exemplos/servicos_ti_teste.json base
```

Cenários: `base` (27,0% — referência oficial RFB) · `otimista` (26,5%) ·
`conservador` (27,5%) · `pessimista` (28,5%).
Saídas em `saidas/<empresa>/`: matriz CSV (2026–2033 × regimes) + resumo Markdown.

## Estrutura

```
parametros/parametros_reforma.json  ← FONTE ÚNICA de alíquotas/regras (versionada)
parametros/CHANGELOG.md             ← histórico de toda mudança normativa
motor/perfil_fiscal.py              ← schema do perfil fiscal (entrada única)
motor/regime_atual.py               ← Agente 2: Simples / Presumido / Real vigentes
motor/ibs_cbs.py                    ← Agente 3: IBS/CBS + cronograma de transição
motor/precificacao.py               ← repasse de preço para manter a margem (por dentro × por fora)
motor/simulador.py                  ← CLI: matriz comparativa + resumo
exemplos/                           ← perfis fiscais (2 empresas fictícias de validação)
empresas/                           ← empresas reais em análise (fora do git, ver empresas/README.md)
.claude/skills/iniciar/              ← comando /iniciar — entrevista + orquestra todo o processo
.claude/skills/simulador-reforma/   ← skill orquestradora da simulação
.claude/agents/ingestao-documentos.md   ← classifica documentos e monta o perfil fiscal
.claude/agents/atualizacao-normativa.md ← agente que atualiza parâmetros por norma nova
```

## Atualização normativa (pilar do projeto)

Nenhum número tributário existe no código Python — tudo vive em
`parametros_reforma.json`. Quando o governo publicar alíquota/regra nova:

1. Diga ao Claude: *"saiu a norma X, atualize o simulador"* → o agente
   `atualizacao-normativa` propõe o diff do JSON com base legal;
2. Você aprova → versão incrementada, CHANGELOG registrado, suíte de validação
   roda automaticamente nos dois perfis de teste.

Cada simulação grava a versão de parâmetros usada — relatórios antigos permanecem
reproduzíveis e auditáveis.

## Status das fases

- **Fase 1 — concluída:** parâmetros versionados, motores de cálculo, perfil fiscal,
  validação com 2 empresas fictícias.
- **Fase 2 — concluída:** ingestão de XMLs de NF-e (`motor/ingestao_xml.py`) + agente
  `ingestao-documentos` (DRE/BP/folha/PGDAS), classificação automática de documentos
  jogados numa pasta única por nome/conteúdo (`motor/classificador_documentos.py`,
  pasta `empresas/<empresa>/novos/`), repartição do DAS por faixa exata,
  split payment/capital de giro (`motor/fluxo_caixa.py`), créditos de transição
  (`motor/transicao_creditos.py`), teste do cliente B2B (`motor/teste_cliente.py`)
  e checagens de coerência (`motor/validacao.py`).
- **Fase 3 — concluída:** sensibilidade ±20% em receita e compras creditáveis
  (`motor/sensibilidade.py`, captura mudança de faixa/anexo/fator R), relatório HTML
  autocontido com identidade Mappi (`motor/relatorio_html.py` — logo, gráfico SVG,
  cards executivos, sem dependências), reduções próprias dos regimes específicos
  da LC 214 (hotelaria −40%, transporte −40%, locação −70%, alienação −50%).
  Versão DOCX para cliente: pedir ao Claude ("gere o DOCX do relatório de <empresa>"),
  que converte via skill de documentos.
- **Repasse de preço — quantificado (`motor/precificacao.py`):** para cada ano e
  regime, calcula o aumento (ou redução) de preço necessário para manter a margem
  líquida de tributos sobre consumo, isolando o efeito da virada de mecânica
  ICMS/ISS "por dentro" → IBS/CBS "por fora" com crédito integral não-cumulativo.
  Antes era só uma menção qualitativa no relatório; agora sai como tabela ano ×
  regime no resumo Markdown, seção no relatório HTML e CSV próprio
  (`repasse_preco_<cenario>.csv`). Modelo a volume constante, sem elasticidade de
  demanda — repasse *necessário*, não previsão de aceitação de mercado.
- **Fase 4 — concluída e TESTADA CONTRA A CALCULADORA OFICIAL REAL:** o módulo
  offline da Receita (V0042 – 1.3.0) está instalado em `calculadora-oficial/`
  e roda via Docker. Iniciar/parar:
  ```bash
  ./calculadora-oficial/iniciar-macos.sh
  ```
  ```bash
  ./calculadora-oficial/parar-macos.sh
  ```
  A validação (`motor/validacao_oficial.py <perfil> --itens <itens.json>`)
  compara item a item (NCM/NBS, CST × cClassTrib, data do fato gerador) a
  alíquota do motor com a oficial (`POST /api/calculadora/regime-geral`,
  localhost:8080) e gera espelho de divergências por empresa — pega erro de
  classificação de redutor e até NCM defasado (a calculadora valida contra a
  TIPI vigente e retorna 404). A calculadora oficial **valida e abastece
  parâmetros; nunca calcula por dentro do motor**.
- **Backlog (Fase 5):** regimes de alíquota própria (combustíveis, financeiro,
  planos de saúde, ZFM), NFS-e na ingestão, dashboard interativo multi-cliente.

## Versionamento

Releases do **código** (motores, skills, agentes) seguem [SemVer](https://semver.org/lang/pt-BR/)
via tags git, com uma GitHub Release por tag:

- **MAJOR:** mudança que quebra o formato do perfil fiscal ou das saídas (CSV/JSON).
- **MINOR:** funcionalidade nova compatível com o que já existe (ex.: v1.2.0 — repasse de preço).
- **PATCH:** correção de bug sem mudar comportamento esperado.

```bash
git tag -a vX.Y.Z -m "vX.Y.Z - resumo da entrega"
git push origin main --follow-tags
gh release create vX.Y.Z --title "..." --notes "..."
```

Isso é **independente** da versão em `parametros/parametros_reforma.json`
(`"versao": "2026.08.5"`), que rastreia mudanças normativas (alíquotas, regras)
e é atualizada pelo agente `atualizacao-normativa` — uma release de código pode
não mexer em parâmetro nenhum, e vice-versa.

## Configurando em outra máquina

1. Clone o repositório e garanta Python 3.9+ (sem dependências externas).
2. A Calculadora oficial NÃO vem no repositório (254 MB): baixe em
   [piloto-cbs.tributos.gov.br](https://piloto-cbs.tributos.gov.br/) → Calculadora
   Offline → "Baixar programa" (Docker), salve como `calculadora.zip` na raiz do
   projeto e extraia para `calculadora-oficial/` (`unzip calculadora.zip -d calculadora-oficial`).
3. Com Docker instalado, rode `./calculadora-oficial/iniciar-macos.sh`
   (no Linux, use os scripts oficiais em `calculadora-oficial/linux/`).
4. Confira o alinhamento: `python3 motor/validacao_oficial.py --dados-abertos`.

**LGPD:** a pasta `saidas/` e perfis de clientes reais (`exemplos/cliente_*.json`)
estão no `.gitignore` e nunca sobem ao repositório.

## Ressalva

Alíquotas de referência pendentes de fixação; regulamentação em andamento.
Estimativas de planejamento — não substituem a análise do contador responsável (CRC).
