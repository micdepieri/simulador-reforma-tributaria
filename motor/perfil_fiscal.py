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
    "categoria_redutor": "padrao",  # chave de redutores_lc214 (vale para a receita fora do mix_redutores)
    # Classificação item a item pela base oficial da Receita (motor/base_oficial.py classificar):
    # [{"cclasstrib", "descricao", "reducao_cbs", "reducao_ibs", "participacao", "fonte"}, ...]
    # participacao = fração da receita; soma <= 1. Vazio = usa só categoria_redutor.
    "mix_redutores": [],
    "classificacao_oficial": None,  # carimbo da classificação: {versao_banco, data_referencia, participacao_nao_modelada}
    "qualificacoes_fornecedor": [], # atores oficiais que a EMPRESA atende (ex.: "conselho profissional") — habilita reduções do art. 127 etc.
    "regime_especifico": None,      # chave de regimes_especificos_lc214, se houver
    "sujeito_imposto_seletivo": False,
    # carga EFETIVA atual (ponto 3 do escopo: benefícios fiscais → usar o efetivo pago)
    "aliquota_efetiva_icms": 0.0,   # sobre receita; 0 para serviços puros
    "aliquota_efetiva_iss": 0.0,    # sobre receita; 0 para comércio puro
    "aliquota_efetiva_ipi": 0.0,
    "aliquota_efetiva_cpp": None,   # INSS patronal sobre a folha (Presumido/Real); None = usa encargos_patronais.aliquota_cpp_padrao
    "aliquota_efetiva_pis_cofins_cumulativo": None,  # PIS+COFINS combinado sobre a receita, SEM crédito sobre compras — usar quando regime_atual="real" mas a empresa apura PIS/COFINS pelo regime CUMULATIVO por opção/benefício (ex.: Lei 10.833/2003 art. 10, receitas de desenvolvimento de software). None = mantém o cálculo não-cumulativo padrão do Lucro Real (lucro_real.pis/.cofins sobre receita - compras_creditaveis_anual).
    "irpj_csll_anual_override": None,  # {"irpj": valor, "csll": valor} — substitui o IRPJ/CSLL calculado pela fórmula padrão do regime_atual. Usar quando o perfil consolida CNPJs com regimes de IRPJ/CSLL DIFERENTES entre si (ex.: uma unidade no Real e outra no Presumido, cada uma apurando separadamente) — os valores devem vir de carga_real()/carga_presumido() rodados à parte para cada unidade e somados, nunca calculados fora do motor. Documentar a memória de cálculo em observacoes. None = usa o cálculo padrão do regime_atual sobre o perfil consolidado inteiro.
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
    # domínio fechado como o do regime: sem isso, uma atividade desconhecida só
    # aparece lá na frente, como KeyError dentro das tabelas de presunção
    if perfil["atividade"] not in ("comercio", "industria", "servicos"):
        raise ValueError("atividade deve ser comercio, industria ou servicos (recebido: %r)"
                         % perfil["atividade"])
    if perfil["regime_atual"] == "simples" and not perfil["anexo_simples"]:
        raise ValueError("anexo_simples é obrigatório quando regime_atual = simples")
    _validar_mix(perfil.get("mix_redutores") or [])
    return perfil


def _validar_mix(mix):
    soma = 0.0
    for m in mix:
        for campo in ("cclasstrib", "reducao_cbs", "reducao_ibs", "participacao"):
            if campo not in m:
                raise ValueError("mix_redutores: item sem '%s' (%r)" % (campo, m))
        for campo in ("reducao_cbs", "reducao_ibs", "participacao"):
            if not 0.0 <= float(m[campo]) <= 1.0:
                raise ValueError("mix_redutores: %s fora de [0, 1] no cClassTrib %s" % (campo, m["cclasstrib"]))
        soma += float(m["participacao"])
    if soma > 1.0001:
        raise ValueError("mix_redutores: participações somam %.4f (> 1)" % soma)


def carregar_parametros(caminho=None):
    if caminho is None:
        caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "parametros", "parametros_reforma.json")
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)
