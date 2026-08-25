# -*- coding: utf-8 -*-
"""Relatório HTML da simulação — identidade Mappi (Fase 3).

Gera arquivo autocontido (logo em base64, gráfico em SVG inline, zero
dependências externas) pronto para enviar ao cliente ou abrir no navegador.
"""
import base64
import os

CORES_REGIME = {
    "simples_cheio": "#7c0040",     # vinho
    "simples_hibrido": "#00a878",   # verde-água
    "presumido": "#6366f1",         # índigo
    "real": "#6b7280",              # cinza
}
ROTULOS = {
    "simples_cheio": "Simples cheio", "simples_hibrido": "Simples híbrido",
    "presumido": "Lucro Presumido", "real": "Lucro Real",
}


def _brl(v):
    return ("R$ %s" % f"{v:,.0f}").replace(",", ".")


def _logo_b64():
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "assets", "logo-principal.png")
    if not os.path.exists(caminho):
        return ""
    with open(caminho, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _grafico_svg(matriz, anos, receita):
    """Linha da carga (% da receita) por regime, 2026-2033."""
    regimes = sorted({r for l in matriz.values() for r in l})
    series = {r: [100.0 * matriz[a][r]["total"] / receita for a in anos if r in matriz[a]]
              for r in regimes}
    todos = [v for vs in series.values() for v in vs]
    y_min, y_max = min(todos), max(todos)
    folga = max(1.0, (y_max - y_min) * 0.15)
    y_min, y_max = max(0, y_min - folga), y_max + folga
    W, H, ML, MR, MT, MB = 860, 380, 62, 20, 20, 46

    def px(i):
        return ML + i * (W - ML - MR) / (len(anos) - 1)

    def py(v):
        return MT + (H - MT - MB) * (1 - (v - y_min) / (y_max - y_min))

    partes = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" '
              'style="width:100%%;height:auto;font-family:inherit">' % (W, H)]
    # grade horizontal + rótulos do eixo Y
    passos = 5
    for k in range(passos + 1):
        v = y_min + k * (y_max - y_min) / passos
        y = py(v)
        partes.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#e5e7eb" stroke-width="1"/>' % (ML, y, W - MR, y))
        partes.append('<text x="%d" y="%.1f" font-size="12" fill="#6b7280" text-anchor="end">%.1f%%</text>' % (ML - 8, y + 4, v))
    # eixo X
    for i, a in enumerate(anos):
        partes.append('<text x="%.1f" y="%d" font-size="12" fill="#6b7280" text-anchor="middle">%d</text>' % (px(i), H - MB + 24, a))
    # séries
    for r in regimes:
        cor = CORES_REGIME.get(r, "#1f2937")
        pontos = " ".join("%.1f,%.1f" % (px(i), py(v)) for i, v in enumerate(series[r]))
        partes.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2.5" stroke-linejoin="round"/>' % (pontos, cor))
        for i, v in enumerate(series[r]):
            partes.append('<circle cx="%.1f" cy="%.1f" r="3.2" fill="%s"/>' % (px(i), py(v), cor))
    partes.append("</svg>")
    legenda = "".join(
        '<span style="display:inline-flex;align-items:center;gap:6px;margin-right:18px;font-size:13px;color:#1f2937">'
        '<span style="width:14px;height:3px;background:%s;display:inline-block;border-radius:2px"></span>%s</span>'
        % (CORES_REGIME.get(r, "#1f2937"), ROTULOS.get(r, r)) for r in regimes)
    return "".join(partes), legenda


def gerar(perfil, params, cenario, matriz, indicadores, sens, anos, caminho):
    receita = perfil["receita_bruta_anual"]
    regimes = sorted({r for l in matriz.values() for r in l})
    cen = params["cenarios_aliquota"][cenario]
    svg, legenda = _grafico_svg(matriz, anos, receita)

    carga_2026 = min(matriz[anos[0]][r]["total"] for r in matriz[anos[0]])
    melhor_2033 = min(matriz[2033].items(), key=lambda kv: kv[1]["total"])
    pior_2033 = max(matriz[2033].items(), key=lambda kv: kv[1]["total"])
    economia = pior_2033[1]["total"] - melhor_2033[1]["total"]
    cli = indicadores["teste_cliente_b2b"]
    split = indicadores["split_payment_2033"]

    def card(titulo, valor, sub, cor="#7c0040"):
        return ('<div style="flex:1;min-width:190px;background:#fff;border:1px solid #eee;'
                'border-top:4px solid %s;border-radius:10px;padding:16px 18px">'
                '<div style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.04em">%s</div>'
                '<div style="font-size:24px;font-weight:700;color:#1f2937;margin-top:4px">%s</div>'
                '<div style="font-size:12px;color:#6b7280;margin-top:4px">%s</div></div>') % (cor, titulo, valor, sub)

    linhas_matriz = []
    for a in anos:
        cels = []
        melhor_r = min(matriz[a].items(), key=lambda kv: kv[1]["total"])[0]
        for r in regimes:
            if r in matriz[a]:
                t = matriz[a][r]["total"]
                marca = "background:#e6f7f1;font-weight:700;" if r == melhor_r else ""
                cels.append('<td style="padding:8px 12px;text-align:right;%s">%s<br><span style="color:#6b7280;font-size:11px">%.1f%%</span></td>'
                            % (marca, _brl(t), 100 * t / receita))
            else:
                cels.append('<td style="padding:8px 12px;text-align:center">—</td>')
        linhas_matriz.append('<tr style="background:%s"><td style="padding:8px 12px;font-weight:600">%d</td>%s</tr>'
                             % ("#fdf8f9" if a % 2 else "#fff", a, "".join(cels)))

    linhas_sens = []
    for s in sens:
        if "erro" in s:
            linhas_sens.append('<tr><td colspan="4" style="padding:8px 12px;color:#ef4444">%s: %s</td></tr>' % (s["variacao"], s["erro"]))
            continue
        linhas_sens.append('<tr style="background:%s"><td style="padding:8px 12px">%s</td>'
                           '<td style="padding:8px 12px;text-align:right">%s</td>'
                           '<td style="padding:8px 12px">%s</td>'
                           '<td style="padding:8px 12px;text-align:right">%s (%.1f%%)</td></tr>'
                           % ("#fdf8f9" if len(linhas_sens) % 2 else "#fff", s["variacao"], _brl(s["receita"]),
                              ROTULOS.get(s["melhor_regime"], s["melhor_regime"]), _brl(s["melhor_total"]), s["carga_pct"]))

    alertas_html = ""
    if indicadores["alertas_validacao"]:
        itens = "".join("<li>%s</li>" % a for a in indicadores["alertas_validacao"])
        alertas_html = ('<div style="background:#fef3c7;border-left:4px solid #f59e0b;border-radius:8px;'
                        'padding:14px 18px;margin:24px 0"><strong style="color:#92400e">Alertas de consistência dos dados</strong>'
                        '<ul style="margin:8px 0 0 18px;color:#92400e">%s</ul></div>') % itens

    repasse = indicadores.get("repasse_preco") or {}
    linhas_repasse = []
    for a in anos:
        cels = []
        for r in regimes:
            item = repasse.get(a, {}).get(r)
            if not item or item.get("repasse_pct") is None:
                cels.append('<td style="padding:8px 12px;text-align:center">n/d</td>')
            else:
                v = item["repasse_pct"]
                cor = "#ef4444" if v > 0 else ("#10b981" if v < 0 else "#6b7280")
                cels.append('<td style="padding:8px 12px;text-align:right;color:%s;font-weight:600">%+.1f%%</td>' % (cor, v))
        linhas_repasse.append('<tr style="background:%s"><td style="padding:8px 12px;font-weight:600">%d</td>%s</tr>'
                              % ("#fdf8f9" if a % 2 else "#fff", a, "".join(cels)))
    cab_repasse = "".join('<th style="padding:10px 12px;text-align:right">%s</th>' % ROTULOS.get(r, r) for r in regimes)
    repasse_html = ""
    if repasse:
        repasse_html = ("""
  <section style="background:#fff;border:1px solid #eee;border-radius:12px;padding:20px 22px;margin-top:22px;overflow-x:auto">
    <h2 style="color:#7c0040;font-size:17px;margin:0 0 4px">Repasse de preço necessário para manter a margem atual</h2>
    <p style="color:#6b7280;font-size:13px;margin:0 0 12px">Aumento (vermelho) ou redução (verde) necessário no preço de venda em cada ano, considerando a virada de ICMS/ISS "por dentro" para IBS/CBS "por fora" com crédito integral. Modelo a volume constante — ver premissas.</p>
    <table style="border-collapse:collapse;width:100%%;font-size:13px">
      <thead><tr style="background:#7c0040;color:#fff">
        <th style="padding:10px 12px;text-align:left">Ano</th>%(cab_regimes)s
      </tr></thead>
      <tbody>%(linhas)s</tbody>
    </table>
  </section>""") % {"cab_regimes": cab_repasse, "linhas": "".join(linhas_repasse)}

    teste_cliente_html = ""
    if cli["receita_b2b"] > 0 and "simples_cheio" in regimes:
        teste_cliente_html = ('<div style="background:#fdf8f9;border:1px solid #7c0040;border-radius:10px;padding:18px;margin:24px 0">'
                              '<h3 style="color:#7c0040;margin:0 0 8px">Teste do cliente B2B (2033)</h3>'
                              '<p style="margin:4px 0">Crédito ao cliente em regime normal/híbrido: <strong>%s/ano</strong> · '
                              'no Simples cheio: <strong>%s/ano</strong></p>'
                              '<p style="margin:4px 0">Custo comercial de permanecer no Simples cheio: '
                              '<strong style="color:#7c0040">%s/ano</strong> em créditos que seus clientes PJ deixam de tomar.</p></div>'
                              ) % (_brl(cli["credito_cliente_hibrido_ou_regime_normal"]),
                                   _brl(cli["credito_cliente_simples_cheio"]),
                                   _brl(cli["custo_comercial_simples_cheio"]))

    avisos = "".join("<li>%s</li>" % a for a in params["avisos"])
    logo = _logo_b64()
    logo_html = ('<img src="data:image/png;base64,%s" alt="Mappi" style="height:56px">' % logo) if logo else ""

    html = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Simulação Reforma Tributária — %(nome)s</title></head>
<body style="margin:0;background:#fdf8f9;color:#1f2937;font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;line-height:1.5">
<div style="max-width:960px;margin:0 auto;padding:28px 20px 60px">
  <header style="display:flex;align-items:center;gap:18px;background:#fff;border-radius:12px;padding:18px 24px;border-bottom:4px solid #7c0040">
    %(logo)s
    <div>
      <h1 style="margin:0;font-size:22px;color:#7c0040">Simulação da Reforma Tributária</h1>
      <div style="color:#6b7280;font-size:14px">%(nome)s · Cenário %(cenario)s (IBS+CBS %(aliq).2f%%) · Parâmetros v%(versao)s</div>
    </div>
  </header>

  <div style="display:flex;gap:14px;flex-wrap:wrap;margin:22px 0">
    %(cards)s
  </div>

  <section style="background:#fff;border:1px solid #eee;border-radius:12px;padding:20px 22px">
    <h2 style="color:#7c0040;font-size:17px;margin:0 0 4px">Carga tributária na transição (%% da receita)</h2>
    <div style="margin:6px 0 10px">%(legenda)s</div>
    %(svg)s
  </section>

  <section style="background:#fff;border:1px solid #eee;border-radius:12px;padding:20px 22px;margin-top:22px;overflow-x:auto">
    <h2 style="color:#7c0040;font-size:17px;margin:0 0 12px">Carga anual estimada por regime</h2>
    <table style="border-collapse:collapse;width:100%%;font-size:13px">
      <thead><tr style="background:#7c0040;color:#fff">
        <th style="padding:10px 12px;text-align:left">Ano</th>%(cab_regimes)s
      </tr></thead>
      <tbody>%(linhas_matriz)s</tbody>
    </table>
    <div style="color:#6b7280;font-size:12px;margin-top:8px">Célula destacada = menor carga do ano.</div>
  </section>

  %(repasse)s

  %(teste_cliente)s

  <div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:22px">
    <section style="flex:1;min-width:300px;background:#fff;border:1px solid #eee;border-radius:12px;padding:20px 22px">
      <h2 style="color:#7c0040;font-size:17px;margin:0 0 8px">Split payment — capital de giro (2033)</h2>
      <p style="margin:4px 0">Float perdido: <strong>%(dias)d dias</strong> sobre o débito de IBS/CBS</p>
      <p style="margin:4px 0">Capital de giro adicional: <strong>%(giro)s</strong></p>
      <p style="margin:4px 0">Custo financeiro anual (%(taxa).0f%% a.a.): <strong>%(custo_fin)s</strong></p>
    </section>
    <section style="flex:1;min-width:300px;background:#fff;border:1px solid #eee;border-radius:12px;padding:20px 22px">
      <h2 style="color:#7c0040;font-size:17px;margin:0 0 8px">Indicadores estruturais</h2>
      <p style="margin:4px 0">Folha/receita: <strong>%(folha).1f%%</strong> (folha não gera crédito de IBS/CBS)</p>
      <p style="margin:4px 0">Compras creditáveis/receita: <strong>%(compras).1f%%</strong></p>
      <p style="margin:4px 0">Mix B2B: <strong>%(b2b).0f%%</strong> · Redutor LC 214: <strong>−%(red).0f%%</strong></p>
    </section>
  </div>

  <section style="background:#fff;border:1px solid #eee;border-radius:12px;padding:20px 22px;margin-top:22px;overflow-x:auto">
    <h2 style="color:#7c0040;font-size:17px;margin:0 0 12px">Sensibilidade — melhor regime em 2033</h2>
    <table style="border-collapse:collapse;width:100%%;font-size:13px">
      <thead><tr style="background:#7c0040;color:#fff">
        <th style="padding:10px 12px;text-align:left">Variação</th>
        <th style="padding:10px 12px;text-align:right">Receita</th>
        <th style="padding:10px 12px;text-align:left">Melhor regime</th>
        <th style="padding:10px 12px;text-align:right">Carga 2033</th>
      </tr></thead>
      <tbody>%(linhas_sens)s</tbody>
    </table>
  </section>

  %(alertas)s

  <section style="background:#5a002f;color:#fff;border-radius:12px;padding:20px 24px;margin-top:26px">
    <h2 style="font-size:16px;margin:0 0 8px">Premissas e ressalvas</h2>
    <ul style="margin:0 0 0 18px;font-size:13px;opacity:.92">
      %(avisos)s
      <li>2026: recolhimento-teste compensável com PIS/COFINS — efeito líquido zero cumprindo as obrigações acessórias.</li>
      <li>Estimativa de planejamento baseada em regulamentação em andamento; não substitui a análise do contador responsável (CRC).</li>
    </ul>
  </section>

  <footer style="color:#6b7280;font-size:12px;text-align:center;margin-top:26px">
    Mappi Soluções em Contabilidade · Curitiba/PR · www.mappi.com.br · Parâmetros v%(versao)s (%(data)s)
  </footer>
</div></body></html>"""

    cards = "".join([
        card("Carga atual (2026)", "%.1f%%" % (100 * carga_2026 / receita), _brl(carga_2026) + "/ano"),
        card("Melhor regime 2033", ROTULOS.get(melhor_2033[0], melhor_2033[0]),
             "%s/ano (%.1f%%)" % (_brl(melhor_2033[1]["total"]), 100 * melhor_2033[1]["total"] / receita), "#00a878"),
        card("Economia vs pior opção", _brl(economia) + "/ano",
             "diferença entre melhor e pior regime em 2033", "#10b981"),
        card("Crédito B2B em jogo", _brl(cli["custo_comercial_simples_cheio"]) + "/ano"
             if cli["receita_b2b"] > 0 and "simples_cheio" in regimes else "n/a",
             "créditos dos clientes PJ (Simples cheio × híbrido)", "#f59e0b"),
    ])
    cab = "".join('<th style="padding:10px 12px;text-align:right">%s</th>' % ROTULOS.get(r, r) for r in regimes)

    conteudo = html % {
        "nome": perfil["nome"], "cenario": cenario, "aliq": cen["total"] * 100,
        "versao": params["versao"], "data": params["data_vigencia"], "logo": logo_html,
        "cards": cards, "legenda": legenda, "svg": svg, "cab_regimes": cab,
        "linhas_matriz": "".join(linhas_matriz), "linhas_sens": "".join(linhas_sens),
        "repasse": repasse_html,
        "teste_cliente": teste_cliente_html, "alertas": alertas_html, "avisos": avisos,
        "dias": split["dias_float_perdidos"], "giro": _brl(split["capital_giro_adicional"]),
        "taxa": 100 * split["taxa_capital_giro_aa"], "custo_fin": _brl(split["custo_financeiro_anual"]),
        "folha": 100 * indicadores["folha_sobre_receita"],
        "compras": 100 * indicadores["compras_creditaveis_sobre_receita"],
        "b2b": 100 * indicadores["mix_b2b"], "red": 100 * indicadores["reducao_lc214"],
    }
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return caminho
