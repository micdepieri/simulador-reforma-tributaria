# -*- coding: utf-8 -*-
"""Relatório editorial da simulação — identidade Mappi.

Gera um documento paginado em A4 (capa + seções), autocontido (logo em
base64, gráfico em SVG inline, fontes do sistema, zero dependências),
pensado para ser lido na tela e impresso/salvo em PDF pelo navegador
(Ctrl+P > Salvar como PDF) sem quebrar tabelas ao meio.

É a peça que vai ao CLIENTE: versão executiva. Os alertas de consistência
dos dados e as lacunas de extração ficam no resumo Markdown, que é o
documento de trabalho do contador.
"""
import base64
import os
from string import Template

# Paleta oficial Mappi
VINHO = "#7c0040"
BORDO = "#5a002f"
ROSA = "#a8325c"
VERDE = "#00a878"
GRAFITE = "#1f2937"
CINZA = "#6b7280"
OFFWHITE = "#fdf8f9"
SUCESSO = "#10b981"
ERRO = "#ef4444"

CORES_REGIME = {
    "simples_cheio": VINHO,
    "simples_hibrido": VERDE,
    "presumido": "#6366f1",
    "real": CINZA,
}
ROTULOS = {
    "simples_cheio": "Simples cheio", "simples_hibrido": "Simples híbrido",
    "presumido": "Lucro Presumido", "real": "Lucro Real",
}
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")


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
    W, H, ML, MR, MT, MB = 860, 400, 64, 24, 24, 48

    def px(i):
        return ML + i * (W - ML - MR) / (len(anos) - 1)

    def py(v):
        return MT + (H - MT - MB) * (1 - (v - y_min) / (y_max - y_min))

    partes = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" '
              'style="width:100%%;height:auto;font-family:inherit">' % (W, H)]
    passos = 5
    for k in range(passos + 1):
        v = y_min + k * (y_max - y_min) / passos
        y = py(v)
        partes.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#e9e2e4" stroke-width="1"/>'
                      % (ML, y, W - MR, y))
        partes.append('<text x="%d" y="%.1f" font-size="13" fill="%s" text-anchor="end">%.1f%%</text>'
                      % (ML - 10, y + 4, CINZA, v))
    for i, a in enumerate(anos):
        partes.append('<text x="%.1f" y="%d" font-size="13" fill="%s" text-anchor="middle">%d</text>'
                      % (px(i), H - MB + 26, CINZA, a))
    for r in regimes:
        cor = CORES_REGIME.get(r, GRAFITE)
        pontos = " ".join("%.1f,%.1f" % (px(i), py(v)) for i, v in enumerate(series[r]))
        partes.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2.6" '
                      'stroke-linejoin="round" stroke-linecap="round"/>' % (pontos, cor))
        for i, v in enumerate(series[r]):
            partes.append('<circle cx="%.1f" cy="%.1f" r="3.4" fill="#fff" stroke="%s" stroke-width="2"/>'
                          % (px(i), py(v), cor))
    partes.append("</svg>")
    legenda = "".join(
        '<span class="chave"><span class="swatch" style="background:%s"></span>%s</span>'
        % (CORES_REGIME.get(r, GRAFITE), ROTULOS.get(r, r)) for r in regimes)
    return "".join(partes), legenda


CSS = """
*{box-sizing:border-box}
body{margin:0;background:#e8e3e4;color:#1f2937;line-height:1.55;
     font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}
.pagina{width:210mm;min-height:297mm;margin:0 auto 10mm;padding:18mm 17mm 14mm;
        background:#fff;position:relative;box-shadow:0 2px 18px rgba(0,0,0,.14)}
h1,h2,h3,.serif{font-family:Georgia,'Iowan Old Style','Times New Roman',serif;font-weight:400}
.kicker{font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:#7c0040;
        font-weight:700;margin:0 0 6px}
h2{font-size:27px;line-height:1.2;color:#1f2937;margin:0 0 10px}
h3{font-size:16px;color:#7c0040;margin:0 0 6px}
.fio{height:3px;background:#7c0040;width:54px;margin:0 0 18px}
.lead{font-size:15.5px;color:#374151;margin:0 0 20px;max-width:56em}
p{margin:0 0 11px}
small,.nota{font-size:11.5px;color:#6b7280;line-height:1.5}

/* cabecalho e rodape corridos */
.topo{display:flex;justify-content:space-between;align-items:baseline;
      border-bottom:1px solid #eee;padding-bottom:7px;margin-bottom:20px;
      font-size:10.5px;color:#6b7280;letter-spacing:.02em}
.topo b{color:#7c0040;font-weight:700}
.rodape{position:absolute;left:17mm;right:17mm;bottom:9mm;display:flex;
        justify-content:space-between;font-size:10px;color:#9ca3af;
        border-top:1px solid #f0eaec;padding-top:6px}

/* capa */
.capa{background:#fdf8f9;display:flex;flex-direction:column}
.capa .marca{display:flex;align-items:center;gap:14px;margin-bottom:auto}
.capa .marca img{height:62px}
.capa .marca span{font-size:12px;color:#6b7280;line-height:1.35}
.capa-titulo{font-size:47px;line-height:1.08;color:#7c0040;margin:0 0 16px;max-width:15em}
.capa-empresa{font-size:22px;color:#1f2937;margin:0;font-weight:600}
.capa-meta{margin-top:26px;padding-top:16px;border-top:2px solid #7c0040;
           display:flex;flex-wrap:wrap;gap:26px}
.capa-meta div{font-size:12px;color:#6b7280}
.capa-meta b{display:block;font-size:14px;color:#1f2937;margin-top:2px;font-weight:600}
.selo{display:inline-block;border:1px solid #7c0040;color:#7c0040;border-radius:999px;
      padding:4px 13px;font-size:10.5px;letter-spacing:.13em;text-transform:uppercase;
      font-weight:700;margin-bottom:22px}

/* numeros grandes */
.stats{display:flex;gap:11px;flex-wrap:wrap;margin:0 0 22px}
.stat{flex:1 1 40%;min-width:150px;border-top:3px solid #7c0040;background:#fdf8f9;
      padding:13px 15px 15px}
.stat .rot{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:#6b7280;font-weight:700}
.stat .val{font-size:29px;line-height:1.1;color:#1f2937;margin-top:5px;
           font-family:Georgia,serif}
.stat .sub{font-size:11.5px;color:#6b7280;margin-top:4px}

/* tabelas */
table{border-collapse:collapse;width:100%;font-size:12.5px}
thead th{background:#7c0040;color:#fff;padding:9px 11px;text-align:right;font-weight:600;
         font-size:11.5px;letter-spacing:.02em}
thead th:first-child{text-align:left}
tbody td{padding:8px 11px;text-align:right;border-bottom:1px solid #f3eef0}
tbody td:first-child{text-align:left;font-weight:600}
tbody tr:nth-child(odd){background:#fdf8f9}
.melhor{background:#e6f7f1 !important;font-weight:700;color:#065f46}
.pct{display:block;font-size:10.5px;color:#6b7280;font-weight:400}

/* blocos */
.destaque{background:#fdf8f9;border-left:4px solid #7c0040;padding:15px 18px;margin:18px 0}
.destaque h3{margin-top:0}
.duas{display:flex;gap:16px;flex-wrap:wrap}
.duas>div{flex:1 1 44%;min-width:210px}
.chave{display:inline-flex;align-items:center;gap:7px;margin-right:18px;font-size:12px}
.swatch{width:15px;height:3px;border-radius:2px;display:inline-block}
.lista{margin:0;padding-left:17px;font-size:12px;color:#4b5563}
.lista li{margin-bottom:5px}
.assinatura{margin-top:30px;padding-top:14px;border-top:1px solid #e5e7eb;font-size:12px;color:#6b7280}
.assinatura .linha{margin-top:34px;border-top:1px solid #9ca3af;width:64%;padding-top:6px}
.evitar{break-inside:avoid;page-break-inside:avoid}

@media print{
  body{background:#fff}
  .pagina{margin:0;box-shadow:none;width:auto;min-height:0;height:297mm;
          page-break-after:always}
  .pagina:last-child{page-break-after:auto}
  .aviso-tela{display:none}
}
@page{size:A4 portrait;margin:0}
@media screen{body{padding:14px 0}}
"""

AVISO_TELA = ('<div class="aviso-tela" style="max-width:210mm;margin:0 auto 10px;padding:9px 14px;'
              'background:#fff;border-left:4px solid #00a878;font-size:12px;color:#374151">'
              'Para gerar o PDF: <b>Ctrl+P</b> &rarr; Destino <b>Salvar como PDF</b> &rarr; '
              'em Mais definições, marque <b>Gráficos de segundo plano</b> e deixe margens em '
              '<b>Padrão</b>. O documento já está paginado em A4.</div>')


def _pagina(num, total, empresa, conteudo):
    return Template("""
<section class="pagina">
  <div class="topo"><span><b>Diagnóstico da Reforma Tributária</b></span><span>$empresa</span></div>
  $conteudo
  <div class="rodape"><span>Mappi Soluções em Contabilidade</span><span>$num / $total</span></div>
</section>""").substitute(empresa=empresa, conteudo=conteudo, num=num, total=total)


def _veredito(perfil, matriz, anos, receita):
    """Frases factuais derivadas dos números — sem conclusão inventada."""
    ano_fim = anos[-1]
    melhor = min(matriz[ano_fim].items(), key=lambda kv: kv[1]["total"])
    pior = max(matriz[ano_fim].items(), key=lambda kv: kv[1]["total"])
    atual = {"simples": "simples_cheio", "presumido": "presumido", "real": "real"}[perfil["regime_atual"]]
    carga_ini = min(matriz[anos[0]][r]["total"] for r in matriz[anos[0]])
    nome_melhor = ROTULOS.get(melhor[0], melhor[0])

    texto = ("Com as alíquotas em vigor plenamente aplicadas em %d, o regime de menor carga "
             "para a empresa é o <b>%s</b>, com %s por ano — o equivalente a %.1f%% da receita. "
             % (ano_fim, nome_melhor, _brl(melhor[1]["total"]),
                100 * melhor[1]["total"] / receita))
    if atual in matriz[ano_fim]:
        carga_atual_fim = matriz[ano_fim][atual]["total"]
        dif = carga_atual_fim - melhor[1]["total"]
        if melhor[0] == atual:
            texto += ("O regime em que a empresa está hoje já é o mais eficiente entre os "
                      "analisados — a decisão é de manutenção, não de mudança.")
        else:
            texto += ("Permanecer no regime atual (%s) custaria %s a mais por ano nesse cenário, "
                      "uma diferença de %.1f%% sobre a receita."
                      % (ROTULOS.get(atual, atual), _brl(dif), 100 * dif / receita))
    else:
        texto += ("O regime atual da empresa deixa de ser elegível no horizonte analisado, "
                  "o que torna a escolha do novo enquadramento uma decisão obrigatória.")
    return {
        "texto": texto,
        "melhor": melhor, "pior": pior, "carga_ini": carga_ini,
        "economia": pior[1]["total"] - melhor[1]["total"],
    }


def gerar(perfil, params, cenario, matriz, indicadores, sens, anos, caminho):
    receita = perfil["receita_bruta_anual"]
    regimes = sorted({r for l in matriz.values() for r in l})
    cen = params["cenarios_aliquota"][cenario]
    svg, legenda = _grafico_svg(matriz, anos, receita)
    v = _veredito(perfil, matriz, anos, receita)
    cli = indicadores["teste_cliente_b2b"]
    split = indicadores["split_payment_2033"]
    empresa = perfil["nome"]
    ano_fim = anos[-1]

    import datetime
    hoje = datetime.date.today()
    data_extenso = "%d de %s de %d" % (hoje.day, MESES[hoje.month - 1], hoje.year)

    cab = "".join("<th>%s</th>" % ROTULOS.get(r, r) for r in regimes)

    # ---------- capa ----------
    logo = _logo_b64()
    logo_img = ('<img src="data:image/png;base64,%s" alt="Mappi">' % logo) if logo else ""
    capa = Template("""
<section class="pagina capa">
  <div class="marca">$logo<span><b>Mappi Soluções em Contabilidade</b><br>Curitiba/PR · www.mappi.com.br</span></div>
  <div style="margin:auto 0">
    <div class="selo">Diagnóstico exclusivo</div>
    <h1 class="capa-titulo">A Reforma Tributária na sua empresa</h1>
    <p class="capa-empresa">$empresa</p>
    <p style="color:#6b7280;font-size:14px;margin-top:6px;max-width:34em">
      O que muda entre 2026 e $ano_fim, quanto custa cada caminho e o que
      precisa ser decidido — em números, a partir dos seus próprios dados.</p>
  </div>
  <div class="capa-meta">
    <div>Emissão<b>$data</b></div>
    <div>Cenário de alíquota<b>$cenario · IBS+CBS $aliq%</b></div>
    <div>Base normativa<b>EC 132/2023 · LC 214/2025</b></div>
    <div>Parâmetros<b>v$versao</b></div>
  </div>
</section>""").substitute(
        logo=logo_img, empresa=empresa, ano_fim=ano_fim, data=data_extenso,
        cenario=cenario.capitalize(), aliq="%.2f" % (cen["total"] * 100), versao=params["versao"])

    # ---------- p2: o que muda ----------
    credito_b2b = (_brl(cli["custo_comercial_simples_cheio"])
                   if cli["receita_b2b"] > 0 and "simples_cheio" in regimes else "—")
    p2 = Template("""
  <p class="kicker">O que muda</p>
  <h2>A conta da transição, em quatro números</h2>
  <div class="fio"></div>
  <p class="lead">$veredito</p>
  <div class="stats">
    <div class="stat"><div class="rot">Carga em $ano_ini</div><div class="val">$carga_ini_pct%</div>
      <div class="sub">$carga_ini por ano, na melhor opção disponível</div></div>
    <div class="stat" style="border-top-color:#00a878"><div class="rot">Melhor regime em $ano_fim</div>
      <div class="val" style="font-size:24px">$melhor_nome</div>
      <div class="sub">$melhor_valor por ano · $melhor_pct% da receita</div></div>
    <div class="stat" style="border-top-color:#10b981"><div class="rot">Diferença entre caminhos</div>
      <div class="val">$economia</div>
      <div class="sub">por ano, entre a melhor e a pior escolha em $ano_fim</div></div>
    <div class="stat" style="border-top-color:#f59e0b"><div class="rot">Crédito em jogo com clientes PJ</div>
      <div class="val" style="font-size:24px">$credito_b2b</div>
      <div class="sub">créditos que seus clientes deixam de tomar no Simples cheio</div></div>
  </div>
  <div class="destaque evitar">
    <h3>Por que a decisão não pode esperar 2033</h3>
    <p style="font-size:13px;margin:0">A transição é gradual: CBS e IBS entram em regime de teste em 2026,
    a CBS substitui PIS/COFINS em 2027 e o IBS sobe em degraus até 2033, enquanto ICMS e ISS caem.
    Cada ano tem uma combinação diferente de tributos — e o regime mais barato pode mudar no meio do
    caminho. As páginas seguintes mostram ano a ano.</p>
  </div>""").substitute(
        veredito=v["texto"], ano_ini=anos[0], ano_fim=ano_fim,
        carga_ini_pct="%.1f" % (100 * v["carga_ini"] / receita), carga_ini=_brl(v["carga_ini"]),
        melhor_nome=ROTULOS.get(v["melhor"][0], v["melhor"][0]),
        melhor_valor=_brl(v["melhor"][1]["total"]),
        melhor_pct="%.1f" % (100 * v["melhor"][1]["total"] / receita),
        economia=_brl(v["economia"]), credito_b2b=credito_b2b)

    # ---------- p3: curva ----------
    p3 = Template("""
  <p class="kicker">A curva da transição</p>
  <h2>Quanto da receita vai para tributos, ano a ano</h2>
  <div class="fio"></div>
  <p class="lead">Cada linha é um regime. A leitura importante não é o ponto final, e sim o
  formato da curva: onde ela sobe, onde cruza outra linha e em que ano a ordem se inverte.</p>
  <div style="margin:4px 0 14px">$legenda</div>
  $svg
  <p class="nota" style="margin-top:14px">Percentual sobre a receita bruta anual, mantendo o volume
  atual de operações. Inclui tributos sobre consumo e sobre o lucro, conforme o regime.</p>""").substitute(
        legenda=legenda, svg=svg)

    # ---------- p4: matriz ----------
    linhas = []
    for a in anos:
        melhor_r = min(matriz[a].items(), key=lambda kv: kv[1]["total"])[0]
        cels = []
        for r in regimes:
            if r in matriz[a]:
                t = matriz[a][r]["total"]
                classe = ' class="melhor"' if r == melhor_r else ""
                cels.append('<td%s>%s<span class="pct">%.1f%%</span></td>'
                            % (classe, _brl(t), 100 * t / receita))
            else:
                cels.append('<td style="color:#9ca3af">—</td>')
        linhas.append("<tr><td>%d</td>%s</tr>" % (a, "".join(cels)))
    p4 = Template("""
  <p class="kicker">Comparativo</p>
  <h2>Carga anual estimada por regime</h2>
  <div class="fio"></div>
  <p class="lead">Valor devido em cada ano da transição e o peso sobre a receita.
  A célula em verde marca o regime de menor carga daquele ano.</p>
  <table class="evitar"><thead><tr><th>Ano</th>$cab</tr></thead><tbody>$linhas</tbody></table>
  <p class="nota" style="margin-top:12px">Projeção a volume constante, sem elasticidade de demanda.
  Valores em reais por ano; o percentual abaixo de cada valor é a fração da receita bruta.</p>""").substitute(
        cab=cab, linhas="".join(linhas))

    # ---------- p5: preco e margem ----------
    repasse = indicadores.get("repasse_preco") or {}
    p5 = ""
    if repasse:
        lr = []
        for a in anos:
            cels = []
            for r in regimes:
                item = repasse.get(a, {}).get(r)
                if not item or item.get("repasse_pct") is None:
                    cels.append('<td style="color:#9ca3af">n/d</td>')
                else:
                    val = item["repasse_pct"]
                    cor = ERRO if val > 0 else (SUCESSO if val < 0 else CINZA)
                    cels.append('<td style="color:%s;font-weight:700">%+.1f%%</td>' % (cor, val))
            lr.append("<tr><td>%d</td>%s</tr>" % (a, "".join(cels)))
        p5 = Template("""
  <p class="kicker">Preço e margem</p>
  <h2>Quanto o preço precisaria mudar para manter a margem</h2>
  <div class="fio"></div>
  <p class="lead">ICMS e ISS são cobrados "por dentro" do preço; IBS e CBS serão cobrados "por fora",
  com crédito integral na cadeia. Essa troca de mecânica muda a margem mesmo sem alteração de custo.
  A tabela mostra o ajuste de preço necessário para preservar a margem atual.</p>
  <table class="evitar"><thead><tr><th>Ano</th>$cab</tr></thead><tbody>$linhas</tbody></table>
  <p class="nota" style="margin-top:12px">Em vermelho, aumento necessário; em verde, espaço para redução.
  Modelo a volume constante, com compras creditáveis fixas em reais. É o repasse <b>necessário</b> para
  manter a margem — não uma previsão de aceitação do mercado nem recomendação de preço.</p>""").substitute(
            cab=cab, linhas="".join(lr))

    # ---------- p6: caixa e clientes ----------
    b2b_html = ""
    if cli["receita_b2b"] > 0 and "simples_cheio" in regimes:
        b2b_html = Template("""
  <div class="destaque evitar">
    <h3>O que seus clientes PJ enxergam</h3>
    <p style="font-size:13px">Empresa em regime normal ou no Simples híbrido transfere
    <b>$credito_normal por ano</b> em créditos aos clientes. No Simples cheio, transfere
    <b>$credito_simples</b>.</p>
    <p style="font-size:13px;margin:0">A diferença — <b style="color:#7c0040">$custo por ano</b> — é o crédito
    que o cliente PJ deixa de tomar ao comprar de você. Não aparece na sua apuração, mas aparece
    na decisão de compra dele.</p>
  </div>""").substitute(
            credito_normal=_brl(cli["credito_cliente_hibrido_ou_regime_normal"]),
            credito_simples=_brl(cli["credito_cliente_simples_cheio"]),
            custo=_brl(cli["custo_comercial_simples_cheio"]))

    p6 = Template("""
  <p class="kicker">Caixa e relações comerciais</p>
  <h2>Dois efeitos que não aparecem na alíquota</h2>
  <div class="fio"></div>
  <p class="lead">A reforma muda também <i>quando</i> o dinheiro sai e <i>como</i> sua empresa é vista
  por quem compra de você. Os dois efeitos são financeiros, e nenhum deles está na conta do imposto.</p>
  <div class="duas evitar">
    <div>
      <h3>Split payment</h3>
      <p style="font-size:13px">O tributo passa a ser retido no momento da liquidação financeira, e
      não no vencimento da apuração. A empresa perde <b>$dias dias</b> de float sobre o débito de IBS/CBS.</p>
      <p style="font-size:13px">Capital de giro adicional necessário: <b>$giro</b><br>
      Custo financeiro anual a $taxa% a.a.: <b style="color:#7c0040">$custo_fin</b></p>
    </div>
    <div>
      <h3>Perfil estrutural</h3>
      <p style="font-size:13px">Folha sobre receita: <b>$folha%</b><br>
      <span class="nota">Salários não geram crédito de IBS/CBS — quanto maior a folha, menor o crédito.</span></p>
      <p style="font-size:13px">Compras creditáveis sobre receita: <b>$compras%</b><br>
      Vendas para PJ: <b>$mixb2b%</b> · Redução setorial aplicada: <b>−$red%</b></p>
    </div>
  </div>
  $bloco_b2b""").substitute(
        dias=split["dias_float_perdidos"], giro=_brl(split["capital_giro_adicional"]),
        taxa="%.0f" % (100 * split["taxa_capital_giro_aa"]),
        custo_fin=_brl(split["custo_financeiro_anual"]),
        folha="%.1f" % (100 * indicadores["folha_sobre_receita"]),
        compras="%.1f" % (100 * indicadores["compras_creditaveis_sobre_receita"]),
        mixb2b="%.0f" % (100 * indicadores["mix_b2b"]),
        red="%.0f" % (100 * indicadores["reducao_lc214"]),
        bloco_b2b=b2b_html)

    # ---------- p7: cenarios ----------
    ls = []
    for s in sens:
        if "erro" in s:
            ls.append('<tr><td colspan="4" style="color:#9ca3af;font-weight:400">%s: não calculável</td></tr>'
                      % s["variacao"])
            continue
        ls.append("<tr><td>%s</td><td>%s</td><td style='text-align:left'>%s</td><td>%s<span class='pct'>%.1f%%</span></td></tr>"
                  % (s["variacao"], _brl(s["receita"]), ROTULOS.get(s["melhor_regime"], s["melhor_regime"]),
                     _brl(s["melhor_total"]), s["carga_pct"]))
    p7 = Template("""
  <p class="kicker">Teste de resistência</p>
  <h2>A recomendação se sustenta se o cenário mudar?</h2>
  <div class="fio"></div>
  <p class="lead">Nenhuma projeção sobrevive intacta ao ano seguinte. Aqui a receita e as compras
  creditáveis variam 20% para mais e para menos, para mostrar se a escolha de regime muda junto.</p>
  <table class="evitar"><thead><tr><th>Variação testada</th><th>Receita</th>
    <th style="text-align:left">Melhor regime em $ano_fim</th><th>Carga</th></tr></thead>
    <tbody>$linhas</tbody></table>
  <p class="nota" style="margin-top:12px">Quando o melhor regime se repete em todas as linhas, a
  recomendação é robusta. Se ele muda conforme a receita, a decisão precisa ser revisada
  periodicamente — e o ponto de virada merece acompanhamento.</p>""").substitute(
        ano_fim=ano_fim, linhas="".join(ls))

    # ---------- p8: premissas ----------
    avisos = "".join("<li>%s</li>" % a for a in params["avisos"])
    p8 = Template("""
  <p class="kicker">Transparência</p>
  <h2>Premissas, limites e próximos passos</h2>
  <div class="fio"></div>
  <p class="lead">Todo número deste documento vem dos dados da sua empresa combinados com a
  legislação publicada até aqui. O que ainda depende de regulamentação está declarado abaixo.</p>

  <h3>Base de cálculo utilizada</h3>
  <ul class="lista">
    <li>Receita bruta anual: <b>$receita</b> · Regime atual: <b>$regime</b> · Atividade: <b>$atividade</b></li>
    <li>Folha anual: <b>$folha_v</b> · Compras creditáveis: <b>$compras_v</b></li>
    <li>Cenário de alíquota: <b>$cenario</b> (IBS+CBS $aliq%) · Parâmetros v$versao, de $data_param</li>
  </ul>

  <h3 style="margin-top:16px">Ressalvas</h3>
  <ul class="lista">$avisos
    <li>Projeção a volume constante: não incorpora crescimento, sazonalidade nem mudança de mix.</li>
    <li>Estimativa de planejamento tributário. Não substitui a análise do contador responsável
        nem a decisão formal de enquadramento.</li>
  </ul>

  <div class="destaque evitar" style="margin-top:18px;border-left-color:#00a878">
    <h3 style="color:#00a878">Próximos passos sugeridos</h3>
    <ul class="lista" style="margin-top:6px">
      <li>Revisar a classificação fiscal dos produtos e serviços (NCM/NBS) frente ao tratamento da LC 214.</li>
      <li>Mapear fornecedores por regime — compras de optantes do Simples geram crédito limitado.</li>
      <li>Avaliar contratos de longo prazo e tabelas de preço à luz do repasse indicado na página 5.</li>
      <li>Reavaliar esta simulação a cada norma relevante publicada pelo Comitê Gestor do IBS.</li>
    </ul>
  </div>

  <div class="assinatura">
    <p>Documento preparado por <b>Mappi Soluções em Contabilidade</b> para $empresa,
    em $data.</p>
    <div class="linha">Contador responsável · CRC</div>
  </div>""").substitute(
        receita=_brl(receita), regime=perfil["regime_atual"].capitalize(),
        atividade=perfil["atividade"].capitalize(), folha_v=_brl(perfil["folha_anual"]),
        compras_v=_brl(perfil["compras_creditaveis_anual"]), cenario=cenario,
        aliq="%.2f" % (cen["total"] * 100), versao=params["versao"],
        data_param=params["data_vigencia"], avisos=avisos, empresa=empresa, data=data_extenso)

    corpos = [p2, p3, p4] + ([p5] if p5 else []) + [p6, p7, p8]
    total = len(corpos) + 1
    paginas = "".join(_pagina(i + 2, total, empresa, c) for i, c in enumerate(corpos))

    html = Template("""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Diagnóstico da Reforma Tributária — $empresa</title>
<style>$css</style></head><body>
$aviso
$capa
$paginas
</body></html>""").substitute(empresa=empresa, css=CSS, aviso=AVISO_TELA, capa=capa, paginas=paginas)

    with open(caminho, "w", encoding="utf-8") as f:
        f.write(html)
    return caminho
