# -*- coding: utf-8 -*-
"""Créditos de transição (ponto 2 do escopo v2).

- saldo_credor_pis_cofins (perfil): saldo credor existente na extinção de
  PIS/COFINS — compensável com a CBS a partir de 2027 (LC 214), consumido
  ano a ano até esgotar.
- saldo_credor_icms (perfil): saldo credor de ICMS homologado existente ao
  final de 2032 — compensável com IBS em 240 parcelas mensais a partir de 2033
  (12/240 = 5% do saldo por ano; o horizonte da simulação só alcança 2033).

Aplicável apenas a Presumido/Real (Simples não acumula esses saldos).
"""


def aplicar_creditos_transicao(matriz_regime, perfil, anos):
    """Recebe {ano: linha} de um regime (presumido/real) e devolve a matriz
    ajustada + memória de consumo dos saldos."""
    saldo_pc = float(perfil.get("saldo_credor_pis_cofins", 0.0) or 0.0)
    saldo_icms = float(perfil.get("saldo_credor_icms", 0.0) or 0.0)
    memoria = []
    for ano in anos:
        linha = matriz_regime[ano]
        abatido = 0.0
        # PIS/COFINS → compensa com CBS a partir de 2027
        if ano >= 2027 and saldo_pc > 0:
            cbs_ano = linha["memoria_ibs_cbs"]["aliq_cbs"] / max(linha["memoria_ibs_cbs"]["aliq_plena"], 1e-9)
            compensavel = linha["ibs_cbs_liquido"] * cbs_ano
            uso = min(saldo_pc, compensavel)
            saldo_pc -= uso
            abatido += uso
        # ICMS acumulado → 1/240 por mês contra IBS a partir de 2033
        if ano >= 2033 and saldo_icms > 0:
            uso = min(saldo_icms * (12.0 / 240.0), linha["ibs_cbs_liquido"] - abatido)
            uso = max(0.0, uso)
            abatido += uso
        if abatido > 0:
            linha = dict(linha)
            linha["creditos_transicao_abatidos"] = round(abatido, 2)
            linha["total"] = round(linha["total"] - abatido, 2)
            matriz_regime[ano] = linha
            memoria.append({"ano": ano, "abatido": round(abatido, 2),
                            "saldo_pis_cofins_restante": round(saldo_pc, 2)})
    return matriz_regime, memoria
