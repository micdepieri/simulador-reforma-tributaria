# -*- coding: utf-8 -*-
"""Conector opcional do Domínio ERP (Sybase) — monta o perfil fiscal a partir do banco.

É OPCIONAL: sem Domínio, o fluxo normal por documentos (/iniciar) continua valendo.
Nenhum parâmetro tributário mora aqui — só extração e derivação de dados da empresa.

SOMENTE LEITURA: todas as queries são SELECT. O módulo nunca escreve no banco.

Três modos de uso:

  1) Imprimir o SQL pronto para rodar no MCP (sem dependência nenhuma):
     python3 motor/conector_dominio.py --queries 123 [--meses 6] [--desde 2026-03]

  2) Montar o perfil a partir dos resultados salvos das queries:
     python3 motor/conector_dominio.py --extracao empresas/<slug>/extracao_dominio.json \
         --saida empresas/<slug>/perfil_fiscal.json

  3) Extrair direto do banco (exige pyodbc + DSN ODBC configurado na máquina):
     python3 motor/conector_dominio.py --dsn ContabilCloud --empresa 123 [--meses 6] \
         --saida-extracao empresas/<slug>/extracao_dominio.json

O modo 3 é conveniência para quem tem o ODBC local; o modo 1+2 é o caminho
portátil, em que quem fala com o banco é o MCP e o Python só transforma.

JANELA DE ANÁLISE: sempre explícita, nunca "o banco inteiro". O padrão é
MESES_PADRAO (6) meses de competência, suficiente para projetar e barato em
volume de dados. Quando a janela é menor que 12 meses, os valores do perfil
(que são anuais por contrato) saem ANUALIZADOS por regra de três — projeção,
não fato: sazonalidade não é modelada, e é isso que o campo
`anualizacao` da extração e as lacunas do perfil registram.
"""
import datetime
import json
import os
import sys

import perfil_fiscal
import regime_atual


# Empresas de controle interno do escritório — nunca entram em análise de cliente.
EMPRESAS_IGNORADAS = (1, 50010)

# Janela padrão de competências extraídas do Domínio. Seis meses é o ponto de
# equilíbrio: recente o bastante para refletir a operação atual e leve o
# bastante para não puxar anos de movimento. O usuário pode pedir outra.
MESES_PADRAO = 6

# codi_imp -> agrupamento usado para derivar a carga efetiva atual.
IMPOSTOS = {
    1: "icms", 27: "icms_antecipado", 31: "icms_st",
    3: "iss",
    4: "pis", 17: "pis",
    5: "cofins", 19: "cofins",
    6: "csll", 7: "irpj",
    16: "irrf", 44: "simples", 64: "simei", 103: "inss_rb",
}

# --- Elegibilidade ao crédito de IBS/CBS por CFOP de entrada ---
#
# ATENÇÃO: a régua aqui é a da LC 214, não a do ICMS. A não cumulatividade
# plena dá crédito sobre TODA aquisição onerosa usada na atividade econômica,
# inclusive uso e consumo e ativo imobilizado — que no ICMS não davam crédito
# (ou davam parcelado, via CIAP). O que fica de fora é o de uso pessoal
# (a "cesta negativa" do art. 57) e o que não é aquisição onerosa.
#
# A classificação é pelos 3 últimos dígitos do CFOP, que independem de a
# operação ser interna (1xxx), interestadual (2xxx) ou do exterior (3xxx).
CFOP_CREDITAVEL = {
    101, 102, 111, 113, 116, 117, 118, 120, 121, 122, 124, 125, 126, 128,  # compras
    251, 252, 253, 254, 255, 256, 257,          # energia, água, gás, comunicação
    301, 302, 303, 304, 305, 306,               # serviço de comunicação tomado
    351, 352, 353, 354, 355, 356, 360,          # serviço de transporte tomado
    401, 403, 405, 406, 407,                    # compras de mercadoria sujeita a ST
    551, 552, 553, 555, 556, 557,               # ativo imobilizado e uso/consumo
    601, 602, 603, 605, 651, 652, 653, 658, 659, 660, 661, 662, 663, 664,  # combustível
    933,                                        # aquisição de serviço sob ISS
}

# Entradas que NÃO são aquisição onerosa: não geram crédito e, somadas junto,
# inflariam a base. Devolução de venda é estorno de saída, não compra; e
# transferência entre estabelecimentos da mesma empresa não é aquisição.
CFOP_NAO_CREDITAVEL = {
    151, 152, 153, 154, 155, 156, 157, 158, 159,  # transferências
    201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 212,  # devolução de venda
    408, 409,                                     # transferências em ST
    410, 411,                                     # devoluções de venda em ST
    414, 415,                                     # retornos de mercadoria em ST
    503, 504, 505,                                # devolução de exportação
    901, 902, 903, 904, 905, 906, 907, 908, 909, 910, 911, 912, 913, 914,
    915, 916, 917, 918, 919, 920, 921, 922, 923, 924, 925, 926, 931, 932,
    934,                                          # remessas, retornos, comodato, consignação
}


def classificar_cfop(cfop):
    """Devolve 'creditavel', 'nao_creditavel' ou 'revisar' para um CFOP de entrada.

    O fallback é 'revisar', nunca 'creditavel': CFOP que a tabela não conhece
    fica para o contador decidir, em vez de entrar na base por omissão.
    """
    try:
        sufixo = int(cfop) % 1000
    except (TypeError, ValueError):
        return "revisar"
    if sufixo in CFOP_CREDITAVEL:
        return "creditavel"
    if sufixo in CFOP_NAO_CREDITAVEL:
        return "nao_creditavel"
    return "revisar"


# Queries validadas em produção (convenções da skill dominio-contabil-db:
# owner bethadba., SELECT TOP N, JOIN geimposto sempre com i.codi_emp = 1).
QUERIES = {
    "cadastro": """
SELECT e.codi_emp, e.nome_emp, e.apel_emp, e.cgce_emp, e.esta_emp, e.stat_emp,
       p.PERI_PAR AS ultimo_periodo
FROM bethadba.geempre e
LEFT JOIN bethadba.efparametro p ON e.codi_emp = p.CODI_EMP
WHERE e.codi_emp = {codi_emp}
""",
    "impostos_apurados": """
SELECT DISTINCT i.codi_imp, TRIM(i.sigl_imp) AS sigla, TRIM(i.nome_imp) AS imposto
FROM bethadba.efsdoimp s
JOIN bethadba.geimposto i ON s.codi_imp = i.codi_imp AND i.codi_emp = 1
WHERE s.codi_emp = {codi_emp} AND s.sdev_sim > 0
ORDER BY i.codi_imp
""",
    "lucro_real": """
SELECT TOP 12 CODI_EMP, COMPETENCIA, I_CALCULO
FROM bethadba.lrcalculo
WHERE CODI_EMP = {codi_emp}
ORDER BY COMPETENCIA DESC
""",
    "carga_tributaria": """
SELECT s.codi_imp, TRIM(i.sigl_imp) AS sigla, SUM(s.sdev_sim) AS total_devido
FROM bethadba.efsdoimp s
JOIN bethadba.geimposto i ON s.codi_imp = i.codi_imp AND i.codi_emp = 1
WHERE s.codi_emp = {codi_emp}
  AND s.data_sim BETWEEN '{data_ini}' AND '{data_fim}'
  AND s.sdev_sim > 0
GROUP BY s.codi_imp, i.sigl_imp
ORDER BY total_devido DESC
""",
    "faturamento_servicos": """
SELECT YEAR(dser_ser) AS ano, MONTH(dser_ser) AS mes,
       COUNT(*) AS qtd_notas, SUM(vcon_ser) AS faturamento
FROM bethadba.efservicos
WHERE codi_emp = {codi_emp} AND cancelada_ser = 'N'
  AND dser_ser BETWEEN '{data_ini}' AND '{data_fim}'
GROUP BY YEAR(dser_ser), MONTH(dser_ser)
ORDER BY ano, mes
""",
    "faturamento_saidas": """
SELECT YEAR(dsai_sai) AS ano, MONTH(dsai_sai) AS mes,
       COUNT(*) AS qtd_notas, SUM(vcon_sai) AS faturamento, SUM(vprod_sai) AS valor_produtos
FROM bethadba.efsaidas
WHERE codi_emp = {codi_emp} AND cancelada_sai = 'N'
  AND dsai_sai BETWEEN '{data_ini}' AND '{data_fim}'
GROUP BY YEAR(dsai_sai), MONTH(dsai_sai)
ORDER BY ano, mes
""",
    "folha": """
SELECT v.comp_bse AS competencia,
       SUM(CASE WHEN v.tipo_eve = 'P' THEN v.vlor_eve ELSE 0 END) AS proventos
FROM bethadba.fobasesserv v
WHERE v.codi_emp = {codi_emp}
  AND v.comp_bse BETWEEN '{data_ini}' AND '{data_fim}'
GROUP BY v.comp_bse
ORDER BY competencia
""",
    "headcount": """
SELECT COUNT(*) AS total_funcionarios
FROM bethadba.foempregados
WHERE codi_emp = {codi_emp} AND data_dem IS NULL
""",
    # --- entradas: base do crédito de IBS/CBS ---
    # codi_nat É o CFOP da operação no Domínio; efnatureza dá a descrição.
    "entradas_por_cfop": """
SELECT e.codi_nat AS cfop, TRIM(n.nome_nat) AS natureza,
       COUNT(*) AS qtd_notas,
       SUM(e.vcon_ent) AS valor_contabil,
       SUM(e.vprod_ent) AS valor_produtos,
       SUM(e.IPI_ENT) AS ipi,
       SUM(e.ICMS_ST_ENT) AS icms_st
FROM bethadba.efentradas e
LEFT JOIN bethadba.efnatureza n
       ON n.codi_nat = e.codi_nat AND n.versao_nat = e.versao_nat
WHERE e.codi_emp = {codi_emp}
  AND e.dent_ent BETWEEN '{data_ini}' AND '{data_fim}'
GROUP BY e.codi_nat, n.nome_nat
ORDER BY valor_contabil DESC
""",
    # O acumulador é como o escritório classifica a operação na escrita fiscal —
    # é ele que separa insumo de despesa e de uso pessoal quando o CFOP não basta.
    "entradas_por_acumulador": """
SELECT e.codi_acu, TRIM(a.NOME_ACU) AS acumulador,
       COUNT(*) AS qtd_notas, SUM(e.vcon_ent) AS valor_contabil
FROM bethadba.efentradas e
LEFT JOIN bethadba.EFACUMULADOR a
       ON a.CODI_ACU = e.codi_acu AND a.CODI_EMP = e.codi_emp
WHERE e.codi_emp = {codi_emp}
  AND e.dent_ent BETWEEN '{data_ini}' AND '{data_fim}'
GROUP BY e.codi_acu, a.NOME_ACU
ORDER BY valor_contabil DESC
""",
    # A partir de 2026 o Domínio já escritura IBS/CBS por nota. Quando houver
    # movimento aqui, este é o crédito REAL — melhor que qualquer estimativa.
    "entradas_credito_ibs": """
SELECT i.CST, TRIM(i.I_CCLASSTRIB) AS cclasstrib,
       COUNT(*) AS qtd_notas,
       SUM(i.BASE_CALCULO) AS base_calculo, SUM(i.VALOR) AS valor
FROM bethadba.EFENTRADAS_IVA_IBS i
JOIN bethadba.efentradas e
  ON e.codi_emp = i.CODI_EMP AND e.codi_ent = i.CODI_ENT
WHERE i.CODI_EMP = {codi_emp}
  AND e.dent_ent BETWEEN '{data_ini}' AND '{data_fim}'
GROUP BY i.CST, i.I_CCLASSTRIB
ORDER BY valor DESC
""",
    "entradas_credito_cbs": """
SELECT i.CST, TRIM(i.I_CCLASSTRIB) AS cclasstrib,
       COUNT(*) AS qtd_notas,
       SUM(i.BASE_CALCULO) AS base_calculo, SUM(i.VALOR) AS valor
FROM bethadba.EFENTRADAS_IVA_CBS i
JOIN bethadba.efentradas e
  ON e.codi_emp = i.CODI_EMP AND e.codi_ent = i.CODI_ENT
WHERE i.CODI_EMP = {codi_emp}
  AND e.dent_ent BETWEEN '{data_ini}' AND '{data_fim}'
GROUP BY i.CST, i.I_CCLASSTRIB
ORDER BY valor DESC
""",
}

# Catálogo de produtos por NCM — alimenta a classificação de tratamento
# diferenciado (cesta básica, medicamentos, etc.). Opcional: roda sob demanda,
# porque em empresa com catálogo grande o retorno é longo.
QUERY_CATALOGO_NCM = """
SELECT TOP 200 TRIM(p.cncm_pdi) AS ncm, TRIM(p.CODIGO_NBS) AS nbs,
       COUNT(*) AS qtd_itens
FROM bethadba.efprodutos p
WHERE p.codi_emp = {codi_emp} AND p.cncm_pdi IS NOT NULL
GROUP BY p.cncm_pdi, p.CODIGO_NBS
ORDER BY qtd_itens DESC
"""

# Busca do codi_emp por nome/apelido — roda antes de tudo, fora do dict acima
# porque o parâmetro é texto e não o código da empresa.
QUERY_IDENTIFICACAO = """
SELECT codi_emp, nome_emp, apel_emp, cgce_emp, esta_emp, stat_emp
FROM bethadba.geempre
WHERE (nome_emp LIKE '%{termo}%' OR apel_emp LIKE '%{termo}%')
  AND stat_emp = 'A'
  AND codi_emp NOT IN (1, 50010)
"""


def _soma_meses(data, meses):
    """Avança `meses` a partir de uma data no dia 1 (positivo ou negativo)."""
    total = (data.year * 12 + data.month - 1) + meses
    return datetime.date(total // 12, total % 12 + 1, 1)


def periodo(meses=MESES_PADRAO, desde=None):
    """Retorna (data_ini, data_fim, meses) da janela de competência analisada.

    Sem `desde`, a janela termina no último mês fechado (o mês corrente fica de
    fora porque a escrituração ainda está em andamento).
    """
    meses = int(meses)
    if meses < 1:
        raise ValueError("a janela precisa ter ao menos 1 mês de competência")
    if desde:
        partes = desde.split("-")
        ini = datetime.date(int(partes[0]), int(partes[1]), 1)
    else:
        hoje = datetime.date.today()
        fim_exclusivo = datetime.date(hoje.year, hoje.month, 1)  # exclui o mês corrente
        ini = _soma_meses(fim_exclusivo, -meses)
    fim = _soma_meses(ini, meses) - datetime.timedelta(days=1)
    return ini.isoformat(), fim.isoformat(), meses


def montar_queries(codi_emp, meses=MESES_PADRAO, desde=None):
    """Devolve ({nome: sql}, (data_ini, data_fim, meses)) com os parâmetros substituídos."""
    if int(codi_emp) in EMPRESAS_IGNORADAS:
        raise ValueError("codi_emp %s é empresa de controle interno (escritório/rubricas)" % codi_emp)
    data_ini, data_fim, meses = periodo(meses, desde)
    queries = {nome: sql.format(codi_emp=int(codi_emp), data_ini=data_ini, data_fim=data_fim).strip()
               for nome, sql in QUERIES.items()}
    return queries, (data_ini, data_fim, meses)


def _soma(linhas, campo):
    total = 0.0
    for linha in linhas or []:
        valor = linha.get(campo)
        if valor is not None:
            total += float(valor)
    return total


def montar_perfil(extracao):
    """Converte o resultado das queries no perfil fiscal do motor.

    Devolve (perfil, lacunas). As lacunas são campos que o banco não entrega
    com confiança e precisam vir de documento ou de confirmação do usuário —
    nunca são preenchidas por chute.
    """
    lacunas = []
    cadastro = (extracao.get("cadastro") or [{}])[0]
    impostos = {int(i["codi_imp"]) for i in extracao.get("impostos_apurados") or [] if i.get("codi_imp")}

    periodo_ext = extracao.get("periodo") or {}
    meses = int(periodo_ext.get("meses") or MESES_PADRAO)
    fator = 12.0 / meses  # janela -> ano; 1.0 quando a janela já é anual

    receita_servicos = _soma(extracao.get("faturamento_servicos"), "faturamento")
    receita_saidas = _soma(extracao.get("faturamento_saidas"), "faturamento")
    receita = receita_servicos + receita_saidas

    # --- regime tributário (regras da skill dominio-contabil-db) ---
    tem_lucro_real = bool(extracao.get("lucro_real"))
    if 64 in impostos:
        regime = None
        lacunas.append("regime_atual: empresa apura SIMEI (MEI, codi_imp 64) — "
                       "fora do escopo do motor, que cobre simples/presumido/real")
    elif 44 in impostos:
        regime = "simples"
    elif tem_lucro_real:
        regime = "real"
    elif impostos & {6, 7}:
        regime = "presumido"
    else:
        regime = None
        lacunas.append("regime_atual: não identificado em efsdoimp/lrcalculo — confirmar com o usuário")

    # --- atividade predominante ---
    if receita <= 0:
        atividade = None
        lacunas.append("atividade e receita_bruta_anual: nenhum faturamento no período — "
                       "conferir se o período tem movimento escriturado")
    elif receita_servicos / receita >= 0.7:
        atividade = "servicos"
    elif receita_saidas / receita >= 0.7:
        # o banco não distingue comércio de indústria sem o CNAE
        atividade = "comercio"
        lacunas.append("atividade: assumido 'comercio' por predominância de saídas de mercadoria; "
                       "confirmar se é indústria (o banco não distingue sem o CNAE)")
    else:
        atividade = "servicos" if receita_servicos > receita_saidas else "comercio"
        lacunas.append("atividade: receita mista (%.0f%% serviços / %.0f%% mercadorias) — "
                       "confirmar a predominante"
                       % (100 * receita_servicos / receita, 100 * receita_saidas / receita))

    # --- carga efetiva atual, por imposto ---
    carga = {}
    for linha in extracao.get("carga_tributaria") or []:
        chave = IMPOSTOS.get(int(linha.get("codi_imp") or 0))
        if chave:
            carga[chave] = carga.get(chave, 0.0) + float(linha.get("total_devido") or 0)

    def efetiva(chave, base):
        return round(carga.get(chave, 0.0) / base, 6) if base > 0 else 0.0

    folha = _soma(extracao.get("folha"), "proventos")

    # --- compras creditáveis (base do crédito de IBS/CBS) ---
    compras = {"creditavel": 0.0, "nao_creditavel": 0.0, "revisar": 0.0}
    cfops_revisar = []
    for linha in extracao.get("entradas_por_cfop") or []:
        valor = float(linha.get("valor_contabil") or 0)
        classe = classificar_cfop(linha.get("cfop"))
        compras[classe] += valor
        if classe == "revisar" and valor > 0:
            cfops_revisar.append((linha.get("cfop"), (linha.get("natureza") or "").strip(), valor))

    tem_entradas = any(compras.values())
    # o ICMS-ST pago na entrada não é crédito de IBS/CBS, mas também não é
    # custo da mercadoria para este fim — fica só registrado para o contador
    icms_st_entradas = _soma(extracao.get("entradas_por_cfop"), "icms_st")

    # crédito de IBS/CBS já escriturado (competências de 2026 em diante)
    credito_ibs = _soma(extracao.get("entradas_credito_ibs"), "valor")
    credito_cbs = _soma(extracao.get("entradas_credito_cbs"), "valor")

    # O perfil fiscal é anual por contrato; a janela pode ser menor. Anualiza
    # por regra de três e registra que o número é projeção, não fato apurado.
    receita_anual = receita * fator
    origem = "%d mes(es) de competência (%s a %s)" % (
        meses, periodo_ext.get("inicio", "?"), periodo_ext.get("fim", "?"))
    if fator != 1.0:
        origem += ", anualizado x%.2f" % fator

    perfil = {
        "nome": (cadastro.get("nome_emp") or "").strip(),
        "atividade": atividade,
        "regime_atual": regime,
        "receita_bruta_anual": round(receita_anual, 2),
        "rbt12": round(receita_anual, 2),
        "uf": (cadastro.get("esta_emp") or "").strip(),
        "folha_anual": round(folha * fator, 2),
        "compras_creditaveis_anual": round(compras["creditavel"] * fator, 2),
        "aliquota_efetiva_icms": round(efetiva("icms", receita) + efetiva("icms_antecipado", receita), 6),
        "aliquota_efetiva_iss": efetiva("iss", receita_servicos or receita),
        "observacoes": "Perfil extraído do Domínio ERP em %s (codi_emp %s) a partir de %s." % (
            extracao.get("extraido_em", "?"), cadastro.get("codi_emp", "?"), origem),
    }

    if fator != 1.0 and receita > 0:
        lacunas.append("receita_bruta_anual, rbt12 e folha_anual são PROJEÇÃO: %d meses observados "
                       "(R$ %.2f de receita) multiplicados por %.2f. A janela não captura sazonalidade — "
                       "se o negócio tem pico ou vale sazonal, ampliar para 12 meses ou ajustar à mão."
                       % (meses, receita, fator))
        lacunas.append("rbt12 projetado: como a faixa do Simples e o sublimite dependem dele, "
                       "conferir contra o RBT12 real do extrato do PGDAS-D antes de simular")

    # O banco não informa o anexo do Simples. Fora do Simples não preenchemos:
    # o motor presume pela atividade e pelo fator R na hora de montar o
    # comparativo, e alerta no resumo — regra única, em regime_atual.py.
    # No Simples o campo é obrigatório para o perfil sequer carregar, então
    # aqui ele é preenchido pela mesma régua e marcado como a confirmar.
    if regime == "simples":
        # mesma régua do comparativo (regime_atual.anexo_efetivo), para o corte
        # do fator R sair de parametros_reforma.json e não daqui
        perfil["anexo_simples"], _ = regime_atual.anexo_efetivo(
            perfil, perfil_fiscal.carregar_parametros())
        if atividade == "servicos" and receita > 0:
            perfil["observacoes"] += (" Anexo %s presumido pelo fator R de %.1f%% "
                                      "(folha/receita da janela)."
                                      % (perfil["anexo_simples"], 100 * folha / receita))
        lacunas.append("anexo_simples: presumido como '%s' pela atividade — o banco não informa. "
                       "CONFIRMAR no extrato do PGDAS-D antes de simular, porque o anexo muda a "
                       "alíquota inteira (e em serviços o fator R é apurado mês a mês, não na "
                       "média da janela)" % perfil.get("anexo_simples"))
    lacunas.append("cnae_principal: confirmar no cadastro da empresa "
                   "(não coberto pelas queries validadas)")

    if not tem_entradas:
        lacunas.append("compras_creditaveis_anual: nenhuma entrada escriturada na janela — "
                       "conferir se a escrita fiscal de entradas está em dia; sem isso o "
                       "crédito de IBS/CBS fica zerado e o resultado, pessimista demais")
    else:
        base = compras["creditavel"] + compras["nao_creditavel"] + compras["revisar"]
        lacunas.append("compras_creditaveis_anual: de R$ %.2f em entradas na janela, R$ %.2f (%.0f%%) "
                       "foram classificados como creditáveis pelo CFOP, R$ %.2f como não creditáveis "
                       "(devolução/transferência/remessa) e R$ %.2f a revisar. Confira a tabela por "
                       "CFOP antes de simular."
                       % (base, compras["creditavel"], 100 * compras["creditavel"] / base,
                          compras["nao_creditavel"], compras["revisar"]))
        for cfop, natureza, valor in sorted(cfops_revisar, key=lambda x: -x[2])[:10]:
            lacunas.append("  CFOP %s (%s): R$ %.2f sem classificação automática — decidir se gera crédito"
                           % (cfop, natureza or "sem descrição", valor))
        lacunas.append("regime dos fornecedores: não verificado. Aquisição de optante pelo Simples "
                       "dá crédito limitado ao que o fornecedor recolheu, não à alíquota cheia — "
                       "o valor acima assume crédito integral e é, nessa medida, otimista")
        lacunas.append("uso pessoal (art. 57 da LC 214): entradas de uso pessoal de sócios e "
                       "administradores não geram crédito e o CFOP não as distingue — conferir "
                       "a tabela por acumulador")

    if credito_ibs or credito_cbs:
        lacunas.append("a escrita já tem IBS/CBS escriturado na janela (IBS R$ %.2f, CBS R$ %.2f). "
                       "Esse é o crédito REAL do período — use-o para aferir a estimativa por CFOP "
                       "em vez de confiar só na classificação automática." % (credito_ibs, credito_cbs))
    if icms_st_entradas:
        lacunas.append("ICMS-ST de R$ %.2f pago nas entradas da janela — não vira crédito de IBS/CBS; "
                       "avaliar o estoque com ST na virada" % icms_st_entradas)

    lacunas.append("cmv_anual e despesas_operacionais_anual: vêm da DRE/balancete")
    lacunas.append("mix_b2b: vem dos XMLs de saída (motor/ingestao_xml.py) ou de estimativa do cliente")
    if carga.get("icms_st"):
        lacunas.append("ICMS-ST de R$ %.2f apurado como DEVIDO na janela (débito de substituto) — "
                       "tratar à parte, não entra na alíquota efetiva própria" % carga["icms_st"])

    return perfil, lacunas


def extrair_via_odbc(dsn, codi_emp, meses=MESES_PADRAO, desde=None):
    """Modo opcional: executa as queries direto no banco via pyodbc (somente leitura)."""
    try:
        import pyodbc
    except ImportError:
        raise SystemExit("pyodbc não instalado — use o modo --queries + --extracao (via MCP), "
                         "ou instale com: pip install pyodbc")
    queries, (data_ini, data_fim, meses) = montar_queries(codi_emp, meses, desde)
    conn = pyodbc.connect("DSN=%s" % dsn, autocommit=True)
    extracao = {
        "extraido_em": datetime.date.today().isoformat(),
        "fonte": "dominio-odbc:%s" % dsn,
        "codi_emp": int(codi_emp),
        "periodo": {"inicio": data_ini, "fim": data_fim, "meses": meses},
    }
    try:
        cursor = conn.cursor()
        for nome, sql in queries.items():
            try:
                cursor.execute(sql)
                colunas = [c[0] for c in cursor.description]
                extracao[nome] = [dict(zip(colunas, linha)) for linha in cursor.fetchall()]
            except Exception as e:  # tabela ausente em base sem o módulo (ex.: folha)
                extracao[nome] = []
                extracao.setdefault("erros", {})[nome] = str(e)
    finally:
        conn.close()
    return extracao


def main():
    # o console do Windows costuma vir em cp1252 e quebra os acentos do relatório
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    def opt(nome, padrao=None):
        return args[args.index(nome) + 1] if nome in args and args.index(nome) + 1 < len(args) else padrao

    desde = opt("--desde")
    meses = int(opt("--meses", MESES_PADRAO))

    if "--queries" in args:
        codi_emp = opt("--queries")
        queries, (ini, fim, meses) = montar_queries(codi_emp, meses, desde)
        print("-- Domínio ERP | codi_emp %s | %d mes(es) de competência: %s a %s"
              % (codi_emp, meses, ini, fim))
        if meses < 12:
            print("-- Janela menor que 12 meses: o perfil sairá ANUALIZADO x%.2f (projeção)."
                  % (12.0 / meses))
        print("-- Rodar cada bloco em mcp__sybase-cloud__executar_sql e salvar o retorno sob a")
        print("-- chave de mesmo nome em extracao_dominio.json, junto de")
        print('-- "periodo": {"inicio": "%s", "fim": "%s", "meses": %d}. SOMENTE SELECT.\n'
              % (ini, fim, meses))
        for nome, sql in queries.items():
            print("-- [%s]\n%s\n" % (nome, sql))
        return

    if "--dsn" in args:
        extracao = extrair_via_odbc(opt("--dsn"), opt("--empresa"), meses, desde)
        destino = opt("--saida-extracao", "extracao_dominio.json")
        with open(destino, "w", encoding="utf-8") as f:
            json.dump(extracao, f, ensure_ascii=False, indent=2, default=str)
        print("Extração gravada em %s" % destino)
        for nome, erro in (extracao.get("erros") or {}).items():
            print("  aviso: bloco '%s' falhou — %s" % (nome, erro))
        return

    if "--extracao" in args:
        with open(opt("--extracao"), "r", encoding="utf-8") as f:
            extracao = json.load(f)
        perfil, lacunas = montar_perfil(extracao)
        destino = opt("--saida")
        if destino:
            pasta = os.path.dirname(os.path.abspath(destino))
            os.makedirs(pasta, exist_ok=True)
            with open(destino, "w", encoding="utf-8") as f:
                json.dump(perfil, f, ensure_ascii=False, indent=2)
            print("Perfil parcial gravado em %s" % destino)
        else:
            print(json.dumps(perfil, ensure_ascii=False, indent=2))
        print("\nLacunas a resolver antes de simular (%d):" % len(lacunas))
        for item in lacunas:
            print("  - %s" % item)
        return

    print(__doc__)
    sys.exit(1)


if __name__ == "__main__":
    main()
