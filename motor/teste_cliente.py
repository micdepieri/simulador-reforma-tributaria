# -*- coding: utf-8 -*-
"""Teste do cliente B2B (Agente 4 — decisão Simples cheio × híbrido).

Quanto de crédito de IBS/CBS o cliente PJ consegue tomar ao comprar desta
empresa, em cada opção, no regime pleno (2033):

- Simples CHEIO: o adquirente credita apenas o montante de IBS/CBS efetivamente
  recolhido dentro do DAS (LC 214) — aproximado pela parcela do DAS que
  corresponde aos tributos sobre consumo convertidos.
- Simples HÍBRIDO / Presumido / Real: crédito integral pela alíquota destacada
  na nota (com redutor da LC 214, se houver).

A diferença é o "custo comercial" de permanecer no Simples cheio: ou o cliente
pressiona o preço para baixo nesse valor, ou a empresa perde competitividade.
"""
import ibs_cbs


def teste_cliente_b2b(perfil, carga_simples_atual, cenario, params, ano=2033):
    cbs, ibs, _ = ibs_cbs.aliquotas_ano(ano, cenario, params)
    aliq_plena = cbs + ibs
    reducao = params["redutores_lc214"][perfil["categoria_redutor"]]["reducao"]
    receita_b2b = perfil["receita_bruta_anual"] * perfil["mix_b2b"]

    credito_hibrido = receita_b2b * aliq_plena * (1.0 - reducao)
    credito_cheio = 0.0
    if carga_simples_atual and "erro" not in carga_simples_atual:
        frac = carga_simples_atual["memoria"]["fracao_das_tributos_consumo"]
        credito_cheio = carga_simples_atual["total"] * frac * perfil["mix_b2b"]

    return {
        "ano_referencia": ano,
        "receita_b2b": round(receita_b2b, 2),
        "credito_cliente_simples_cheio": round(credito_cheio, 2),
        "credito_cliente_hibrido_ou_regime_normal": round(credito_hibrido, 2),
        "custo_comercial_simples_cheio": round(credito_hibrido - credito_cheio, 2),
    }
