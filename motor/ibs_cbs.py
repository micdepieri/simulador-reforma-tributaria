# -*- coding: utf-8 -*-
"""Motor IBS/CBS (Agente 3): carga na transição 2026-2033 conforme LC 214/2025.

Todas as alíquotas, frações do cronograma e redutores vêm de
parametros_reforma.json — nada hardcoded (pilar de atualização rápida).

Simplificações declaradas (Fase 1):
- Crédito de IBS/CBS calculado à alíquota plena sobre compras_creditaveis_anual
  (entradas na regra geral), mesmo quando a saída tem redutor.
- 2026 (ano-teste): recolhimento compensável com PIS/COFINS → efeito líquido zero
  para quem cumpre as obrigações acessórias; registrado na memória.
- Simples híbrido: DAS reduzido proporcionalmente à fração já substituída do
  cronograma; IBS/CBS por fora em débito−crédito. Repartição por faixa refina na Fase 2.
- Simples cheio: DAS constante durante a transição (LC 123 preservada).
"""


def aliquotas_ano(ano, cenario, params):
    """Retorna (aliq_cbs, aliq_ibs, compensavel) do ano, já com o cronograma aplicado."""
    c = params["cronograma_transicao"][str(ano)]
    cen = params["cenarios_aliquota"][cenario]
    if c.get("cbs_frac_ref") is None:
        cbs = c.get("cbs_teste", 0.0)
    else:
        cbs = cen["cbs"] * c["cbs_frac_ref"] - c.get("cbs_reducao_pp", 0.0)
    if c.get("ibs_frac_ref") is None:
        ibs = c.get("ibs_teste", 0.0)
    else:
        ibs = cen["ibs"] * c["ibs_frac_ref"]
    return cbs, ibs, bool(c.get("teste_compensavel_pis_cofins", False))


def reducoes_saida(perfil, params):
    """(redução_CBS, redução_IBS) da receita de saída, como fração (0.6 = −60%).

    Prioridade:
    1. regime_especifico com redução própria (regimes_especificos_detalhe);
    2. mix_redutores — classificação item a item pela base oficial da Receita
       (motor/base_oficial.py): média ponderada pela participação na receita; a
       fração não coberta pelo mix segue a categoria_redutor;
    3. categoria_redutor única do perfil (comportamento original).
    CBS e IBS podem divergir (ex.: cClassTrib 200025 — CBS −100%, IBS −60%).
    """
    detalhe = params.get("regimes_especificos_detalhe", {})
    if perfil.get("regime_especifico") in detalhe:
        r = detalhe[perfil["regime_especifico"]]["reducao"]
        return r, r
    base = params["redutores_lc214"][perfil["categoria_redutor"]]["reducao"]
    mix = perfil.get("mix_redutores") or []
    if not mix:
        return base, base
    coberto = sum(m["participacao"] for m in mix)
    resto = max(0.0, 1.0 - coberto)
    red_cbs = sum(m["participacao"] * m["reducao_cbs"] for m in mix) + resto * base
    red_ibs = sum(m["participacao"] * m["reducao_ibs"] for m in mix) + resto * base
    return red_cbs, red_ibs


def aliquota_saida(cbs, ibs, perfil, params):
    """Alíquota efetiva de saída (CBS + IBS) depois dos redutores."""
    red_cbs, red_ibs = reducoes_saida(perfil, params)
    return cbs * (1.0 - red_cbs) + ibs * (1.0 - red_ibs)


def ibs_cbs_liquido(perfil, ano, cenario, params):
    """Débito − crédito de IBS/CBS do ano, com redutor da LC 214 na saída."""
    cbs, ibs, compensavel = aliquotas_ano(ano, cenario, params)
    aliq_plena = cbs + ibs
    red_cbs, red_ibs = reducoes_saida(perfil, params)
    aliq_saida = cbs * (1.0 - red_cbs) + ibs * (1.0 - red_ibs)
    # redução equivalente única (para exibição); idêntica à categoria quando não há mix
    reducao = 1.0 - aliq_saida / aliq_plena if aliq_plena else red_cbs
    debito = perfil["receita_bruta_anual"] * aliq_saida
    credito = perfil["compras_creditaveis_anual"] * aliq_plena
    liquido = max(0.0, debito - credito)
    return {
        "aliq_cbs": cbs, "aliq_ibs": ibs, "aliq_plena": aliq_plena,
        "reducao_lc214": reducao, "reducao_cbs": red_cbs, "reducao_ibs": red_ibs,
        "aliq_saida": aliq_saida,
        "debito": round(debito, 2), "credito": round(credito, 2),
        "liquido": round(liquido, 2), "compensavel_teste": compensavel,
    }


def carga_ano_presumido_real(carga_atual, perfil, ano, cenario, params):
    """Carga anual de Presumido ou Real no ano da transição.

    carga_atual: resultado de regime_atual.carga_presumido/carga_real (ano-base).
    Tributos sobre o lucro permanecem; tributos sobre consumo legados são
    escalados pelo cronograma e o IBS/CBS líquido entra por cima.
    """
    c = params["cronograma_transicao"][str(ano)]
    t = carga_atual["tributos"]
    pis_cofins = (t["PIS"] + t["COFINS"]) * c["pis_cofins_vigente"]
    icms_iss = (t["ICMS"] + t["ISS"]) * c["icms_iss_vigente"]
    ipi = t["IPI"] * (1.0 if perfil["zona_franca_manaus"] else c["ipi_vigente"])
    novo = ibs_cbs_liquido(perfil, ano, cenario, params)
    ibs_cbs = 0.0 if novo["compensavel_teste"] else novo["liquido"]
    cpp = carga_atual.get("sobre_folha", 0.0)
    total = carga_atual["sobre_lucro"] + pis_cofins + icms_iss + ipi + ibs_cbs + cpp
    return {
        "ano": ano, "regime": carga_atual["regime"],
        "sobre_lucro": round(carga_atual["sobre_lucro"], 2),
        "pis_cofins_legado": round(pis_cofins, 2),
        "icms_iss_legado": round(icms_iss, 2),
        "ipi_legado": round(ipi, 2),
        "ibs_cbs_liquido": round(ibs_cbs, 2),
        "cpp_patronal": round(cpp, 2),
        "total": round(total, 2),
        "memoria_ibs_cbs": novo,
    }


def aliquotas_simples_ibs_cbs(carga_simples_atual, ano, params):
    """(pCBSSN, pIBSSN) do Simples CHEIO no ano, como fração da receita.

    Mesma premissa do motor: dentro do DAS, a parcela de PIS/COFINS (+IPI) vira CBS e a
    de ICMS/ISS vira IBS na proporção já substituída pelo cronograma da transição. É o
    percentual que a nota do optante destaca (pCBSSN/pIBSSN da NT 2026.005) e, portanto,
    o crédito que o adquirente toma. Na prática virá do PGDAS-D (Receita Integra,
    Release 16); até lá, é a estimativa do motor — validável na Calculadora do Simples.
    """
    c = params["cronograma_transicao"][str(ano)]
    mem = carga_simples_atual["memoria"]
    rep = mem.get("reparticao_consumo_faixa") or \
        params["simples_nacional"]["anexos"][mem["anexo_aplicado"]]["reparticao_consumo"]
    aliq = mem["aliquota_efetiva"]
    frac_pc = rep.get("pis_cofins", 0.0) + rep.get("ipi", 0.0)
    frac_ii = rep.get("icms_iss", 0.0)
    return (aliq * frac_pc * (1.0 - c["pis_cofins_vigente"]),
            aliq * frac_ii * (1.0 - c["icms_iss_vigente"]))


def carga_ano_simples(carga_simples_atual, perfil, ano, cenario, params, hibrido):
    """Carga anual do Simples no ano da transição (cheio ou híbrido)."""
    das = carga_simples_atual["total"]
    if not hibrido:
        return {"ano": ano, "regime": "simples_cheio", "das": round(das, 2),
                "ibs_cbs_liquido": 0.0, "total": round(das, 2)}
    c = params["cronograma_transicao"][str(ano)]
    rep = carga_simples_atual["memoria"].get("reparticao_consumo_faixa")
    if rep is None:
        anexo = carga_simples_atual["memoria"]["anexo_aplicado"]
        rep = params["simples_nacional"]["anexos"][anexo]["reparticao_consumo"]
    frac_pc = rep.get("pis_cofins", 0.0) + rep.get("ipi", 0.0)
    frac_ii = rep.get("icms_iss", 0.0)
    # parcela do DAS já substituída pelo cronograma sai do DAS
    das_hibrido = das * (1.0
                         - frac_pc * (1.0 - c["pis_cofins_vigente"])
                         - frac_ii * (1.0 - c["icms_iss_vigente"]))
    novo = ibs_cbs_liquido(perfil, ano, cenario, params)
    ibs_cbs = 0.0 if novo["compensavel_teste"] else novo["liquido"]
    # na transição, o IBS/CBS por fora só entra na proporção já vigente do cronograma
    total = das_hibrido + ibs_cbs
    return {"ano": ano, "regime": "simples_hibrido",
            "das": round(das_hibrido, 2), "ibs_cbs_liquido": round(ibs_cbs, 2),
            "total": round(total, 2), "memoria_ibs_cbs": novo}
