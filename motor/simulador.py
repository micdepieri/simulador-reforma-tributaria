# -*- coding: utf-8 -*-
"""Simulador da Reforma Tributária — CLI (Fase 1).

Uso:
    python3 motor/simulador.py exemplos/empresa.json [cenario]

cenario: base (padrão) | conservador | pessimista

Saídas em saidas/<nome>/:
    matriz_transicao_<cenario>.csv  — carga anual por regime, 2026-2033
    resumo_<cenario>.md             — resumo executivo com premissas e ressalvas
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import perfil_fiscal
import regime_atual
import ibs_cbs
import fluxo_caixa
import transicao_creditos
import teste_cliente
import validacao
import sensibilidade
import relatorio_html

ANOS = list(range(2026, 2034))


def simular(perfil, params, cenario):
    """Matriz {regime: {ano: linha}} + indicadores."""
    receita = perfil["receita_bruta_anual"]
    base_presumido = regime_atual.carga_presumido(perfil, params)
    base_real = regime_atual.carga_real(perfil, params)
    elegivel_simples = perfil["rbt12"] <= params["simples_nacional"]["limite_anual"]
    base_simples = regime_atual.carga_simples(perfil, params) if elegivel_simples else None

    matriz = {}
    for ano in ANOS:
        linha = {}
        linha["presumido"] = ibs_cbs.carga_ano_presumido_real(base_presumido, perfil, ano, cenario, params)
        linha["real"] = ibs_cbs.carga_ano_presumido_real(base_real, perfil, ano, cenario, params)
        if base_simples and "erro" not in base_simples:
            linha["simples_cheio"] = ibs_cbs.carga_ano_simples(base_simples, perfil, ano, cenario, params, hibrido=False)
            linha["simples_hibrido"] = ibs_cbs.carga_ano_simples(base_simples, perfil, ano, cenario, params, hibrido=True)
        matriz[ano] = linha

    # créditos de transição (Presumido/Real) — consomem saldos ano a ano
    memoria_creditos = {}
    for regime in ("presumido", "real"):
        mr = {ano: matriz[ano][regime] for ano in ANOS}
        mr, mem = transicao_creditos.aplicar_creditos_transicao(mr, perfil, ANOS)
        for ano in ANOS:
            matriz[ano][regime] = mr[ano]
        if mem:
            memoria_creditos[regime] = mem

    # indicadores estruturais (pontos 6 e 7 do escopo v2)
    aliq_plena_2033 = sum(ibs_cbs.aliquotas_ano(2033, cenario, params)[:2])
    detalhe = params.get("regimes_especificos_detalhe", {})
    if perfil.get("regime_especifico") in detalhe:
        reducao = detalhe[perfil["regime_especifico"]]["reducao"]
    else:
        reducao = params["redutores_lc214"][perfil["categoria_redutor"]]["reducao"]
    credito_cliente_pleno = receita * perfil["mix_b2b"] * aliq_plena_2033 * (1 - reducao)

    # Fase 2: split payment (sobre o débito IBS/CBS pleno de 2033) + teste do cliente
    debito_2033 = ibs_cbs.ibs_cbs_liquido(perfil, 2033, cenario, params)["debito"]
    split = fluxo_caixa.impacto_split_payment(debito_2033, params, perfil)
    cliente = teste_cliente.teste_cliente_b2b(perfil, base_simples, cenario, params)
    alertas = validacao.validar_perfil(perfil, params)

    indicadores = {
        "split_payment_2033": split,
        "teste_cliente_b2b": cliente,
        "alertas_validacao": alertas,
        "creditos_transicao": memoria_creditos,
        "folha_sobre_receita": round(perfil["folha_anual"] / receita, 4) if receita else 0.0,
        "compras_creditaveis_sobre_receita": round(perfil["compras_creditaveis_anual"] / receita, 4) if receita else 0.0,
        "mix_b2b": perfil["mix_b2b"],
        "credito_potencial_clientes_2033": round(credito_cliente_pleno, 2),
        "categoria_redutor": perfil["categoria_redutor"],
        "reducao_lc214": reducao,
        "regime_especifico": perfil["regime_especifico"],
        "sujeito_imposto_seletivo": perfil["sujeito_imposto_seletivo"],
    }
    bases = {"presumido": base_presumido, "real": base_real, "simples": base_simples}
    return matriz, indicadores, bases


def gravar_csv(matriz, caminho):
    regimes = sorted({r for linha in matriz.values() for r in linha})
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ano"] + ["total_%s" % r for r in regimes] +
                   ["ibs_cbs_liquido_%s" % r for r in regimes])
        for ano in ANOS:
            linha = matriz[ano]
            w.writerow([ano] +
                       [linha[r]["total"] if r in linha else "" for r in regimes] +
                       [linha[r].get("ibs_cbs_liquido", "") if r in linha else "" for r in regimes])


def gravar_resumo(perfil, params, cenario, matriz, indicadores, bases, caminho):
    cen = params["cenarios_aliquota"][cenario]
    receita = perfil["receita_bruta_anual"]
    linhas = []
    ap = linhas.append
    ap("# Simulação Reforma Tributária — %s" % perfil["nome"])
    ap("")
    ap("**Cenário:** %s (IBS+CBS = %.2f%%) · **Parâmetros:** v%s (%s) · Valores anuais em R$"
       % (cenario, cen["total"] * 100, params["versao"], params["data_vigencia"]))
    ap("")
    ap("## Carga anual estimada por regime (2026–2033)")
    ap("")
    regimes = sorted({r for l in matriz.values() for r in l})
    ap("| Ano | " + " | ".join(regimes) + " |")
    ap("|---|" + "---|" * len(regimes))
    for ano in ANOS:
        cels = []
        for r in regimes:
            if r in matriz[ano]:
                t = matriz[ano][r]["total"]
                cels.append("%s (%.1f%%)" % (f"{t:,.0f}".replace(",", "."), 100 * t / receita))
            else:
                cels.append("—")
        ap("| %d | %s |" % (ano, " | ".join(cels)))
    ap("")
    ap("## Melhor regime por ano")
    ap("")
    for ano in ANOS:
        melhor = min(matriz[ano].items(), key=lambda kv: kv[1]["total"])
        ap("- **%d:** %s (R$ %s)" % (ano, melhor[0], f"{melhor[1]['total']:,.0f}".replace(",", ".")))
    ap("")
    ap("## Indicadores estruturais")
    ap("")
    ap("- Folha/receita: **%.1f%%** (folha não gera crédito de IBS/CBS)" % (100 * indicadores["folha_sobre_receita"]))
    ap("- Compras creditáveis/receita: **%.1f%%**" % (100 * indicadores["compras_creditaveis_sobre_receita"]))
    ap("- Mix B2B: **%.0f%%** — crédito potencial gerado aos clientes em 2033: R$ %s/ano"
       % (100 * indicadores["mix_b2b"], f"{indicadores['credito_potencial_clientes_2033']:,.0f}".replace(",", ".")))
    ap("- Redutor LC 214 aplicado: %s (−%.0f%%)" % (indicadores["categoria_redutor"], 100 * indicadores["reducao_lc214"]))
    split = indicadores["split_payment_2033"]
    ap("")
    ap("## Split payment — impacto no capital de giro (regime pleno 2033)")
    ap("")
    ap("- Float perdido: %d dias sobre o débito de IBS/CBS" % split["dias_float_perdidos"])
    ap("- Capital de giro adicional necessário: **R$ %s**" % f"{split['capital_giro_adicional']:,.0f}".replace(",", "."))
    ap("- Custo financeiro anual estimado (%.0f%% a.a.): **R$ %s**"
       % (100 * split["taxa_capital_giro_aa"], f"{split['custo_financeiro_anual']:,.0f}".replace(",", ".")))
    cli = indicadores["teste_cliente_b2b"]
    if cli["receita_b2b"] > 0:
        ap("")
        ap("## Teste do cliente B2B (2033)")
        ap("")
        ap("- Crédito que o cliente toma se a empresa estiver em regime normal/híbrido: R$ %s/ano"
           % f"{cli['credito_cliente_hibrido_ou_regime_normal']:,.0f}".replace(",", "."))
        if cli["credito_cliente_simples_cheio"] or indicadores.get("regime_especifico") is None:
            ap("- Crédito no Simples CHEIO (limitado ao recolhido no DAS): R$ %s/ano"
               % f"{cli['credito_cliente_simples_cheio']:,.0f}".replace(",", "."))
            ap("- **Custo comercial de permanecer no Simples cheio: R$ %s/ano** "
               "(pressão de preço ou perda de competitividade junto a clientes PJ)"
               % f"{cli['custo_comercial_simples_cheio']:,.0f}".replace(",", "."))
    if indicadores.get("creditos_transicao"):
        ap("")
        ap("## Créditos de transição aplicados")
        ap("")
        for regime, mem in indicadores["creditos_transicao"].items():
            for m in mem:
                ap("- %s %d: R$ %s abatidos (saldo PIS/COFINS restante R$ %s)"
                   % (regime, m["ano"], f"{m['abatido']:,.0f}".replace(",", "."),
                      f"{m['saldo_pis_cofins_restante']:,.0f}".replace(",", ".")))
    if indicadores["alertas_validacao"]:
        ap("")
        ap("## ⚠ Alertas de consistência dos dados")
        ap("")
        for a in indicadores["alertas_validacao"]:
            ap("- %s" % a)
    if indicadores["regime_especifico"]:
        ap("- **Atenção:** regime específico da LC 214 (%s) — cálculo detalhado na Fase 2." % indicadores["regime_especifico"])
    if indicadores["sujeito_imposto_seletivo"]:
        ap("- **Atenção:** atividade sujeita ao Imposto Seletivo (não incluído nos totais — Fase 2).")
    ap("")
    ap("## Premissas e ressalvas")
    ap("")
    for aviso in params["avisos"]:
        ap("- %s" % aviso)
    ap("- 2026: recolhimento-teste compensável com PIS/COFINS — efeito líquido zero para quem cumpre as obrigações acessórias.")
    ap("- Simples cheio: DAS mantido pela LC 123; risco comercial B2B indicado acima.")
    ap("- Repartição do DAS pela faixa exata da LC 123 (conferir tabelas antes de uso em cliente real).")
    ap("- Split payment modelado como perda de float sobre o débito de IBS/CBS; créditos de transição consumidos ano a ano quando informados no perfil.")
    ap("- Estimativa de planejamento; não substitui análise do contador responsável (CRC).")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    caminho_perfil = sys.argv[1]
    cenario = sys.argv[2] if len(sys.argv) > 2 else "base"
    perfil = perfil_fiscal.carregar_perfil(caminho_perfil)
    params = perfil_fiscal.carregar_parametros()
    matriz, indicadores, bases = simular(perfil, params, cenario)

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    slug = perfil["nome"].lower().replace(" ", "_")
    pasta = os.path.join(raiz, "saidas", slug)
    os.makedirs(pasta, exist_ok=True)
    csv_path = os.path.join(pasta, "matriz_transicao_%s.csv" % cenario)
    md_path = os.path.join(pasta, "resumo_%s.md" % cenario)
    html_path = os.path.join(pasta, "relatorio_%s.html" % cenario)
    gravar_csv(matriz, csv_path)
    gravar_resumo(perfil, params, cenario, matriz, indicadores, bases, md_path)
    sens = sensibilidade.rodar(simular, perfil, params, cenario)
    relatorio_html.gerar(perfil, params, cenario, matriz, indicadores, sens, ANOS, html_path)

    print("Simulação concluída — %s (cenário %s, parâmetros v%s)" % (perfil["nome"], cenario, params["versao"]))
    print("CSV:       %s" % csv_path)
    print("Resumo:    %s" % md_path)
    print("Relatório: %s" % html_path)
    print("Sensibilidade (2033): " + "; ".join(
        "%s -> %s" % (s["variacao"], s.get("melhor_regime", "erro")) for s in sens))
    for ano in ANOS:
        melhor = min(matriz[ano].items(), key=lambda kv: kv[1]["total"])
        print("  %d -> melhor: %-16s R$ %14s" % (ano, melhor[0], f"{melhor[1]['total']:,.2f}"))


if __name__ == "__main__":
    main()
