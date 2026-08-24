# -*- coding: utf-8 -*-
"""Perfil fiscal padronizado da empresa — entrada única de todos os motores.

Todos os valores monetários são ANUAIS, em R$.
Nenhum parâmetro tributário mora aqui: alíquotas e regras vêm exclusivamente
de parametros/parametros_reforma.json (fonte única, versionada).
"""
import json
import os


CAMPOS_OBRIGATORIOS = [
    "nome", "atividade", "regime_atual", "receita_bruta_anual",
]

PADROES = {
    # atividade: "comercio" | "industria" | "servicos"
    "cnae_principal": "",
    "uf": "",
    "municipio": "",
    # regime_atual: "simples" | "presumido" | "real"
    "anexo_simples": None,          # "I".."V" quando regime_atual = simples
    "rbt12": None,                  # se None, usa receita_bruta_anual
    "folha_anual": 0.0,             # total bruto (LGPD: apenas totais)
    "cmv_anual": 0.0,
    "despesas_operacionais_anual": 0.0,
    "compras_creditaveis_anual": 0.0,   # entradas que gerariam crédito IBS/CBS (e PIS/COFINS no Real)
    "mix_b2b": 0.5,                 # fração da receita vendida a PJ (crédito importa)
    "categoria_redutor": "padrao",  # chave de redutores_lc214
    "regime_especifico": None,      # chave de regimes_especificos_lc214, se houver
    "sujeito_imposto_seletivo": False,
    # carga EFETIVA atual (ponto 3 do escopo: benefícios fiscais → usar o efetivo pago)
    "aliquota_efetiva_icms": 0.0,   # sobre receita; 0 para serviços puros
    "aliquota_efetiva_iss": 0.0,    # sobre receita; 0 para comércio puro
    "aliquota_efetiva_ipi": 0.0,
    "zona_franca_manaus": False,
    # Fase 2 — split payment e créditos de transição
    "prazo_recolhimento_atual_dias": None,  # None = usa padrão de parametros.financeiro
    "taxa_capital_giro_aa": None,           # None = usa padrão de parametros.financeiro
    "saldo_credor_pis_cofins": 0.0,         # saldo credor na extinção (compensa CBS a partir de 2027)
    "saldo_credor_icms": 0.0,               # saldo homologado ao fim de 2032 (1/240 por mês contra IBS)
    "observacoes": "",
}


def carregar_perfil(caminho):
    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)
    faltando = [c for c in CAMPOS_OBRIGATORIOS if c not in dados]
    if faltando:
        raise ValueError("Perfil fiscal incompleto, faltam campos: %s" % ", ".join(faltando))
    perfil = dict(PADROES)
    perfil.update(dados)
    if perfil["rbt12"] is None:
        perfil["rbt12"] = perfil["receita_bruta_anual"]
    if perfil["regime_atual"] not in ("simples", "presumido", "real"):
        raise ValueError("regime_atual deve ser simples, presumido ou real")
    if perfil["regime_atual"] == "simples" and not perfil["anexo_simples"]:
        raise ValueError("anexo_simples é obrigatório quando regime_atual = simples")
    return perfil


def carregar_parametros(caminho=None):
    if caminho is None:
        caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "parametros", "parametros_reforma.json")
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)
