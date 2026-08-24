# -*- coding: utf-8 -*-
"""Motor do regime atual (Agente 2): carga tributária vigente sobre consumo e lucro.

Calcula a carga anual estimada em cada regime a partir do perfil fiscal.
Retorna dicionários {tributo: valor} + total, para composição do comparativo.

Simplificações declaradas (Fase 1):
- IRPJ/CSLL no Real usam o lucro contábil do perfil (receita - cmv - despesas - folha)
  sem adições/exclusões de LALUR.
- PIS/COFINS não-cumulativos: crédito calculado sobre compras_creditaveis_anual.
- ICMS/ISS/IPI usam as ALÍQUOTAS EFETIVAS do perfil (efetivo pago, capturando
  benefícios fiscais atuais — ponto 3 do escopo v2).
"""


def _faixa_simples(tabela_anexo, rbt12):
    for i, faixa in enumerate(tabela_anexo["faixas"]):
        if rbt12 <= faixa["ate"]:
            return i, faixa
    return None, None  # estourou o limite


def anexo_efetivo(perfil, params):
    """Aplica o fator R quando o anexo informado é III ou V."""
    anexo = perfil["anexo_simples"]
    if anexo in ("III", "V") and perfil["receita_bruta_anual"] > 0:
        fator_r = perfil["folha_anual"] / perfil["rbt12"]
        corte = params["simples_nacional"]["fator_r_corte"]
        anexo = "III" if fator_r >= corte else "V"
    return anexo


def carga_simples(perfil, params):
    sn = params["simples_nacional"]
    rbt12 = perfil["rbt12"]
    receita = perfil["receita_bruta_anual"]
    if rbt12 > sn["limite_anual"]:
        return {"erro": "RBT12 acima do limite do Simples (R$ %.2f)" % sn["limite_anual"]}
    anexo = anexo_efetivo(perfil, params)
    tabela = sn["anexos"][anexo]
    idx, faixa = _faixa_simples(tabela, rbt12)
    aliq_efetiva = (rbt12 * faixa["aliquota"] - faixa["deduzir"]) / rbt12
    das = receita * aliq_efetiva
    # repartição EXATA da faixa (LC 123); fallback para média do anexo
    if "reparticao_faixas" in tabela:
        rep_faixa = tabela["reparticao_faixas"][idx]
        rep = {"pis_cofins": rep_faixa.get("pis", 0.0) + rep_faixa.get("cofins", 0.0),
               "icms_iss": rep_faixa.get("icms_iss", 0.0),
               "ipi": rep_faixa.get("ipi", 0.0)}
        rep = {k: v for k, v in rep.items() if v}
    else:
        rep = tabela["reparticao_consumo"]
    fracao_consumo = sum(rep.values())
    memoria = {
        "anexo_aplicado": anexo,
        "faixa": idx + 1,
        "fator_r": round(perfil["folha_anual"] / rbt12, 4) if rbt12 else None,
        "aliquota_nominal": faixa["aliquota"],
        "parcela_deduzir": faixa["deduzir"],
        "aliquota_efetiva": round(aliq_efetiva, 6),
        "reparticao_consumo_faixa": rep,
        "fracao_das_tributos_consumo": round(fracao_consumo, 6),
    }
    return {
        "regime": "simples",
        "tributos": {"DAS": round(das, 2)},
        "das_parcela_consumo": round(das * fracao_consumo, 2),
        "das_parcela_nao_consumo": round(das * (1 - fracao_consumo), 2),
        "total": round(das, 2),
        "memoria": memoria,
    }


def _irpj_csll(base_irpj, base_csll, params_regime):
    irpj = base_irpj * params_regime["irpj"]
    excedente = max(0.0, base_irpj - params_regime["irpj_adicional_limite_anual"])
    adicional = excedente * params_regime["irpj_adicional"]
    csll = base_csll * params_regime["csll"]
    return irpj, adicional, csll


def carga_presumido(perfil, params):
    lp = params["lucro_presumido"]
    receita = perfil["receita_bruta_anual"]
    ativ = "servicos" if perfil["atividade"] == "servicos" else perfil["atividade"]
    base_irpj = receita * lp["presuncao_irpj"][ativ]
    base_csll = receita * lp["presuncao_csll"][ativ]
    irpj, adicional, csll = _irpj_csll(base_irpj, base_csll, lp)
    pis = receita * lp["pis"]
    cofins = receita * lp["cofins"]
    icms = receita * perfil["aliquota_efetiva_icms"]
    iss = receita * perfil["aliquota_efetiva_iss"]
    ipi = receita * perfil["aliquota_efetiva_ipi"]
    tributos = {
        "IRPJ": round(irpj + adicional, 2), "CSLL": round(csll, 2),
        "PIS": round(pis, 2), "COFINS": round(cofins, 2),
        "ICMS": round(icms, 2), "ISS": round(iss, 2), "IPI": round(ipi, 2),
    }
    return {
        "regime": "presumido",
        "tributos": tributos,
        "sobre_consumo": round(pis + cofins + icms + iss + ipi, 2),
        "sobre_lucro": round(irpj + adicional + csll, 2),
        "total": round(sum(tributos.values()), 2),
        "memoria": {"base_presuncao_irpj": base_irpj, "base_presuncao_csll": base_csll},
    }


def carga_real(perfil, params):
    lr = params["lucro_real"]
    receita = perfil["receita_bruta_anual"]
    lucro = (receita - perfil["cmv_anual"] - perfil["despesas_operacionais_anual"]
             - perfil["folha_anual"])
    base = max(0.0, lucro)
    irpj, adicional, csll = _irpj_csll(base, base, lr)
    base_pc = max(0.0, receita - perfil["compras_creditaveis_anual"])
    pis = base_pc * lr["pis"]
    cofins = base_pc * lr["cofins"]
    icms = receita * perfil["aliquota_efetiva_icms"]
    iss = receita * perfil["aliquota_efetiva_iss"]
    ipi = receita * perfil["aliquota_efetiva_ipi"]
    tributos = {
        "IRPJ": round(irpj + adicional, 2), "CSLL": round(csll, 2),
        "PIS": round(pis, 2), "COFINS": round(cofins, 2),
        "ICMS": round(icms, 2), "ISS": round(iss, 2), "IPI": round(ipi, 2),
    }
    return {
        "regime": "real",
        "tributos": tributos,
        "sobre_consumo": round(pis + cofins + icms + iss + ipi, 2),
        "sobre_lucro": round(irpj + adicional + csll, 2),
        "total": round(sum(tributos.values()), 2),
        "memoria": {"lucro_estimado": round(lucro, 2),
                    "base_pis_cofins_nao_cumulativo": round(base_pc, 2)},
    }
