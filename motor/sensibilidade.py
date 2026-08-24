# -*- coding: utf-8 -*-
"""Análise de sensibilidade ±20% (Fase 3).

Varia receita bruta (±20%, com RBT12 acompanhando — pode mudar faixa/anexo/fator R)
e compras creditáveis (±20%, afeta créditos de IBS/CBS e PIS/COFINS no Real).
Para cada variação, reporta a carga total de 2033 por regime e o melhor regime.
"""
import copy

VARIACOES = [
    ("receita -20%",  {"receita_bruta_anual": 0.8, "rbt12": 0.8, "cmv_anual": 0.8, "compras_creditaveis_anual": 0.8}),
    ("base",          {}),
    ("receita +20%",  {"receita_bruta_anual": 1.2, "rbt12": 1.2, "cmv_anual": 1.2, "compras_creditaveis_anual": 1.2}),
    ("compras -20%",  {"compras_creditaveis_anual": 0.8}),
    ("compras +20%",  {"compras_creditaveis_anual": 1.2}),
]


def rodar(simular_fn, perfil, params, cenario, ano_foco=2033):
    resultados = []
    for rotulo, fatores in VARIACOES:
        p = copy.deepcopy(perfil)
        for campo, fator in fatores.items():
            p[campo] = p[campo] * fator
        try:
            matriz, _, _ = simular_fn(p, params, cenario)
        except Exception as e:
            resultados.append({"variacao": rotulo, "erro": str(e)})
            continue
        linha = matriz[ano_foco]
        melhor = min(linha.items(), key=lambda kv: kv[1]["total"])
        resultados.append({
            "variacao": rotulo,
            "receita": round(p["receita_bruta_anual"], 2),
            "totais_2033": {r: linha[r]["total"] for r in sorted(linha)},
            "melhor_regime": melhor[0],
            "melhor_total": melhor[1]["total"],
            "carga_pct": round(100.0 * melhor[1]["total"] / p["receita_bruta_anual"], 2),
        })
    return resultados
