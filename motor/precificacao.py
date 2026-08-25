# -*- coding: utf-8 -*-
"""Repasse de preço necessário na transição (ponto 12 do escopo v2, agora quantificado).

Pergunta respondida: que preço de venda a empresa precisa praticar em cada ano
da transição para manter a MESMA margem líquida de tributos sobre consumo que
tem hoje, dada a virada de mecânica de cálculo trazida pela reforma?

- Hoje: ICMS/ISS e PIS/COFINS cumulativo (Presumido) são "por dentro" — o
  tributo é um percentual do próprio preço de venda, sem crédito amplo
  (Presumido) ou com crédito parcial (Real). No Simples, o DAS é uma alíquota
  única embutida no preço, sem nenhum crédito ao cliente PJ.
- Na reforma: IBS/CBS são "por fora" — calculados sobre o valor da operação
  SEM incluir o próprio imposto, destacados na nota, com crédito integral e
  não-cumulativo (LC 214 art. 12).

Modelo e simplificações declaradas:
- Volume físico vendido constante — só o preço de venda muda.
- Compras/CMV creditáveis não se alteram com o novo preço de venda (o custo
  de entrada é independente do preço de saída praticado).
- Tributos sobre o LUCRO (IRPJ/CSLL e a fração do DAS que não é consumo)
  ficam FORA da conta — a reforma não altera essa base, e ela já é idêntica
  nos dois lados da equação (cancela). O que muda é só a parte "sobre
  consumo" do preço.
- Ignora elasticidade-preço da demanda: é o repasse *necessário* para manter
  a margem, não uma previsão de quanto o mercado vai aceitar pagar.
- Créditos de transição (saldo PIS/COFINS, saldo ICMS) já abatidos na carga
  do ano (via transicao_creditos) reduzem o tributo devido mas não entram
  nesta conta de crédito de IBS/CBS sobre compras — são fenômenos distintos.

Álgebra (por regime, por ano):
    Net_atual   = receita_atual − tributo_consumo_atual_do_regime (hoje)
    denom       = receita_atual × (1 − legado_frac_ano − aliq_saida_ano)
    indice      = (Net_atual − credito_ano) / denom
    repasse_pct = (indice − 1) × 100

onde legado_frac_ano = tributos legados remanescentes no ano (ainda "por
dentro") / receita_atual; aliq_saida_ano = alíquota de saída do IBS/CBS já
líquida do redutor LC 214; credito_ano = crédito de IBS/CBS sobre
compras_creditaveis_anual (fixo em R$, pela simplificação de custo de entrada
constante).

indice > 1 → preço precisa SUBIR para manter a margem atual.
indice < 1 → preço poderia CAIR e ainda manter a margem atual (comum em
Presumido/Real com boa parcela de compras creditáveis, que hoje não
recuperam ICMS/PIS/COFINS cumulativo e passam a ter crédito pleno).
"""


def _tributo_atual_consumo(regime, bases):
    if regime in ("presumido", "real"):
        return bases[regime]["sobre_consumo"]
    # simples_cheio e simples_hibrido partem do mesmo DAS atual (parcela consumo)
    return bases["simples"]["das_parcela_consumo"]


def _legado_consumo_ano(regime, linha, bases):
    if regime in ("presumido", "real"):
        return linha["pis_cofins_legado"] + linha["icms_iss_legado"] + linha["ipi_legado"]
    if regime == "simples_cheio":
        # DAS mantido pela LC 123 — a parcela consumo não se altera na transição
        return bases["simples"]["das_parcela_consumo"]
    if regime == "simples_hibrido":
        return linha["das"] - bases["simples"]["das_parcela_nao_consumo"]
    raise ValueError("regime desconhecido para repasse de preço: %s" % regime)


def repasse_ano(regime, ano, linha, bases, receita_atual):
    if receita_atual <= 0:
        return {"ano": ano, "regime": regime, "repasse_pct": None,
                "erro": "receita_bruta_anual zerada — repasse não calculável."}
    tributo_atual = _tributo_atual_consumo(regime, bases)
    net_atual = receita_atual - tributo_atual
    legado = _legado_consumo_ano(regime, linha, bases)
    memoria = linha.get("memoria_ibs_cbs")
    aliq_saida = memoria["aliq_saida"] if memoria else 0.0
    credito = memoria["credito"] if memoria else 0.0
    denom = receita_atual - legado - receita_atual * aliq_saida
    if denom <= 0:
        return {"ano": ano, "regime": regime, "repasse_pct": None,
                "erro": "carga projetada consumiria 100%% ou mais da receita neste cenário — "
                        "modelo linear de repasse não se aplica; revisar dados do perfil."}
    indice = (net_atual - credito) / denom
    return {
        "ano": ano, "regime": regime,
        "tributo_atual_consumo": round(tributo_atual, 2),
        "net_atual": round(net_atual, 2),
        "legado_remanescente": round(legado, 2),
        "aliq_saida_ibs_cbs": round(aliq_saida, 6),
        "credito_ibs_cbs": round(credito, 2),
        "indice_preco": round(indice, 6),
        "repasse_pct": round((indice - 1.0) * 100.0, 3),
    }


def calcular(matriz, bases, perfil, anos):
    """Retorna {ano: {regime: repasse_ano(...)}} para todos os anos/regimes da matriz."""
    receita_atual = perfil["receita_bruta_anual"]
    resultado = {}
    for ano in anos:
        resultado[ano] = {
            regime: repasse_ano(regime, ano, linha, bases, receita_atual)
            for regime, linha in matriz[ano].items()
        }
    return resultado


def resumo_regime(precificacao, regime, anos_destaque=(2029, 2033)):
    """Atalho para os anos de maior interesse no relatório (1º degrau e regime pleno)."""
    return {ano: precificacao[ano][regime] for ano in anos_destaque
            if ano in precificacao and regime in precificacao[ano]}
