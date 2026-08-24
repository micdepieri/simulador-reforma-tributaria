# -*- coding: utf-8 -*-
"""Impacto do split payment no capital de giro (ponto 1 do escopo v2).

Modelo declarado (Fase 2):
- Hoje a empresa recebe o valor cheio da venda e recolhe o tributo sobre consumo
  dias depois (float médio = financeiro.prazo_recolhimento_atual_dias).
- Com split payment, o IBS/CBS é retido na liquidação financeira — esse float
  desaparece para a parcela IBS/CBS.
- Capital de giro adicional necessário = IBS/CBS mensal × (float em dias / 30).
- Custo financeiro anual = capital de giro adicional × taxa_capital_giro_aa.

Simplificação: aplica-se apenas à parcela IBS/CBS (débito bruto, pois é o débito
que sofre split; créditos são ressarcidos/compensados em prazo próprio).
"""


def impacto_split_payment(ibs_cbs_debito_anual, params, perfil):
    fin = params.get("financeiro", {})
    dias_float = perfil.get("prazo_recolhimento_atual_dias") or fin.get("prazo_recolhimento_atual_dias", 25)
    taxa = perfil.get("taxa_capital_giro_aa") or fin.get("taxa_capital_giro_aa", 0.15)
    mensal = ibs_cbs_debito_anual / 12.0
    capital_giro = mensal * (dias_float / 30.0)
    custo_financeiro = capital_giro * taxa
    return {
        "dias_float_perdidos": dias_float,
        "capital_giro_adicional": round(capital_giro, 2),
        "custo_financeiro_anual": round(custo_financeiro, 2),
        "taxa_capital_giro_aa": taxa,
    }
