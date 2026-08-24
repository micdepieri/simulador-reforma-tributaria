# -*- coding: utf-8 -*-
"""Checagens de coerência do perfil fiscal (ponto 9 do escopo v2).

Retorna lista de alertas (não bloqueia a simulação; os alertas entram no
resumo — a simulação também funciona como mini-diagnóstico dos dados).
"""


def validar_perfil(perfil, params):
    alertas = []
    receita = perfil["receita_bruta_anual"]
    ap = alertas.append

    if receita <= 0:
        ap("Receita bruta anual zerada ou negativa.")
        return alertas

    soma_custos = perfil["cmv_anual"] + perfil["despesas_operacionais_anual"] + perfil["folha_anual"]
    if soma_custos > receita * 1.05:
        ap("Custos+despesas+folha (%.0f) superam a receita em mais de 5%% — prejuízo relevante ou dado inconsistente; conferir DRE." % soma_custos)

    if perfil["compras_creditaveis_anual"] > receita:
        ap("Compras creditáveis maiores que a receita — conferir XMLs de entrada (devoluções/transferências?).")
    if perfil["atividade"] == "comercio" and perfil["cmv_anual"] > 0 and \
            perfil["compras_creditaveis_anual"] < perfil["cmv_anual"] * 0.5:
        ap("Compras creditáveis muito abaixo do CMV — possível subaproveitamento de créditos ou dado faltando.")

    folha_receita = perfil["folha_anual"] / receita
    if folha_receita > 0.6:
        ap("Folha/receita de %.0f%% — muito alta; conferir se o total inclui encargos ou se há erro." % (100 * folha_receita))

    if perfil["regime_atual"] == "simples":
        if perfil["rbt12"] > params["simples_nacional"]["limite_anual"]:
            ap("RBT12 acima do limite do Simples — empresa deveria estar desenquadrada.")
        elif perfil["rbt12"] > params["simples_nacional"]["limite_anual"] * 0.85:
            ap("RBT12 acima de 85%% do limite do Simples — risco de desenquadramento no horizonte simulado.")
        if perfil["rbt12"] > params["simples_nacional"]["sublimite_icms_iss"]:
            ap("RBT12 acima do sublimite de R$ 3,6 mi — ICMS/ISS fora do DAS; alíquotas efetivas do perfil devem refletir isso.")

    if perfil["atividade"] == "comercio" and perfil["aliquota_efetiva_icms"] == 0 and perfil["regime_atual"] != "simples":
        ap("Comércio fora do Simples com ICMS efetivo = 0 — conferir (benefício total ou dado faltando?).")
    if perfil["atividade"] == "servicos" and perfil["aliquota_efetiva_iss"] == 0 and perfil["regime_atual"] != "simples":
        ap("Serviços fora do Simples com ISS efetivo = 0 — conferir.")

    if not (0.0 <= perfil["mix_b2b"] <= 1.0):
        ap("mix_b2b deve estar entre 0 e 1.")
    if perfil["categoria_redutor"] not in params["redutores_lc214"]:
        ap("categoria_redutor desconhecida: %s" % perfil["categoria_redutor"])
    return alertas
