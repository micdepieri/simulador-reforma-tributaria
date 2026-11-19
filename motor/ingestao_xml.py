# -*- coding: utf-8 -*-
"""Ingestão de XMLs de NF-e (Agente 1 — parte automatizável).

Uso:
    python3 motor/ingestao_xml.py <pasta_com_xmls> <cnpj_da_empresa> [--saida <arquivo.json>]

Varre a pasta, classifica cada NF-e como SAÍDA (emitente = empresa) ou
ENTRADA (destinatário = empresa) e consolida:
- totais por direção (vNF, vProd, vICMS, vIPI, vPIS, vCOFINS)
- receita B2B × B2C (destinatário com CNPJ × CPF) → mix_b2b
- UFs de destino (exposição origem→destino)
- NCMs mais relevantes (para classificar redutores da LC 214)
- receita por NCM com descrições de exemplo + lista "itens_para_classificar", pronta
  para a classificação oficial (motor/base_oficial.py classificar)
- compras por regime do fornecedor (CRT do emitente: Simples × regime normal) e por
  cClassTrib informado nas notas de entrada (2026+) — base do levantamento de créditos
Varre a pasta e as subpastas.

Gera resumo JSON em saidas/ para alimentar o perfil fiscal.
Não interpreta CFOP de devolução/transferência em detalhe (Fase 3);
lista os CFOPs encontrados para revisão do contador.
"""
import json
import os
import sys
import xml.etree.ElementTree as ET

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}


def _txt(el, caminho):
    achado = el.find(caminho, NS)
    return achado.text if achado is not None else None


def _num(el, caminho):
    v = _txt(el, caminho)
    return float(v) if v else 0.0


def ler_nfe(caminho_xml, cnpj_empresa):
    tree = ET.parse(caminho_xml)
    root = tree.getroot()
    inf = root.find(".//nfe:infNFe", NS)
    if inf is None:
        return None
    emit_cnpj = _txt(inf, "nfe:emit/nfe:CNPJ")
    dest_cnpj = _txt(inf, "nfe:dest/nfe:CNPJ")
    dest_cpf = _txt(inf, "nfe:dest/nfe:CPF")
    tot = inf.find("nfe:total/nfe:ICMSTot", NS)
    nota = {
        "arquivo": os.path.basename(caminho_xml),
        "direcao": "saida" if emit_cnpj == cnpj_empresa else "entrada",
        "dest_tipo": "PJ" if dest_cnpj else ("PF" if dest_cpf else "?"),
        "uf_dest": _txt(inf, "nfe:dest/nfe:enderDest/nfe:UF"),
        "vNF": _num(tot, "nfe:vNF") if tot is not None else 0.0,
        "vProd": _num(tot, "nfe:vProd") if tot is not None else 0.0,
        "vICMS": _num(tot, "nfe:vICMS") if tot is not None else 0.0,
        "vIPI": _num(tot, "nfe:vIPI") if tot is not None else 0.0,
        "vPIS": _num(tot, "nfe:vPIS") if tot is not None else 0.0,
        "vCOFINS": _num(tot, "nfe:vCOFINS") if tot is not None else 0.0,
        "cfops": sorted({_txt(det, "nfe:prod/nfe:CFOP") or "" for det in inf.findall("nfe:det", NS)}),
        "ncms": sorted({_txt(det, "nfe:prod/nfe:NCM") or "" for det in inf.findall("nfe:det", NS)}),
        # CRT do emitente: 1 = Simples, 2 = Simples c/ excesso de sublimite, 3 = regime normal, 4 = MEI
        "crt_emitente": _txt(inf, "nfe:emit/nfe:CRT"),
        "itens": [_ler_item(det) for det in inf.findall("nfe:det", NS)],
    }
    return nota


def _ler_item(det):
    """Item da nota: NCM, valor e — nas notas emitidas a partir de 2026 — o grupo
    IBSCBS com CST e cClassTrib (a classificação que o EMITENTE usou)."""
    return {
        "ncm": _txt(det, "nfe:prod/nfe:NCM") or "",
        "xprod": (_txt(det, "nfe:prod/nfe:xProd") or "").strip(),
        "cfop": _txt(det, "nfe:prod/nfe:CFOP") or "",
        "vprod": _num(det, "nfe:prod/nfe:vProd"),
        "cst_ibscbs": _txt(det, "nfe:imposto/nfe:IBSCBS/nfe:CST"),
        "cclasstrib": _txt(det, "nfe:imposto/nfe:IBSCBS/nfe:cClassTrib"),
    }


REGIME_POR_CRT = {"1": "simples", "2": "simples_excesso_sublimite", "3": "regime_normal", "4": "mei"}


def _agrupar_saidas_por_ncm(saidas):
    """Receita por NCM (soma de vProd dos itens) + amostra de descrições e o cClassTrib
    informado nas notas — insumo do motor/base_oficial.py classificar."""
    grupos = {}
    for n in saidas:
        for it in n["itens"]:
            if not it["ncm"]:
                continue
            g = grupos.setdefault(it["ncm"], {"ncm": it["ncm"], "valor": 0.0, "qtd_itens": 0,
                                              "descricoes_exemplo": [], "cclasstrib_nas_notas": {}})
            g["valor"] += it["vprod"]
            g["qtd_itens"] += 1
            if it["xprod"] and it["xprod"] not in g["descricoes_exemplo"] and len(g["descricoes_exemplo"]) < 3:
                g["descricoes_exemplo"].append(it["xprod"])
            if it["cclasstrib"]:
                c = g["cclasstrib_nas_notas"]
                c[it["cclasstrib"]] = round(c.get(it["cclasstrib"], 0.0) + it["vprod"], 2)
    lista = sorted(grupos.values(), key=lambda g: -g["valor"])
    for g in lista:
        g["valor"] = round(g["valor"], 2)
    return lista


def _compras_por_regime_fornecedor(entradas):
    por_regime, por_cclass = {}, {}
    for n in entradas:
        regime = REGIME_POR_CRT.get(n.get("crt_emitente") or "", "desconhecido")
        por_regime[regime] = por_regime.get(regime, 0.0) + n["vProd"]
        for it in n["itens"]:
            if it["cclasstrib"]:
                por_cclass[it["cclasstrib"]] = por_cclass.get(it["cclasstrib"], 0.0) + it["vprod"]
    total = sum(por_regime.values())
    simples = sum(v for k, v in por_regime.items() if k in ("simples", "simples_excesso_sublimite", "mei"))
    return ({k: round(v, 2) for k, v in sorted(por_regime.items(), key=lambda kv: -kv[1])},
            round(simples / total, 4) if total else None,
            {k: round(v, 2) for k, v in sorted(por_cclass.items(), key=lambda kv: -kv[1])})


def consolidar(pasta, cnpj_empresa):
    notas, erros = [], []
    # percorre subpastas também (ex.: documentos/xmls/entrada e /saida do /iniciar)
    arquivos = sorted(os.path.join(raiz, nome) for raiz, _, nomes in os.walk(pasta)
                      for nome in nomes if nome.lower().endswith(".xml"))
    for caminho in arquivos:
        try:
            nota = ler_nfe(caminho, cnpj_empresa)
            if nota:
                notas.append(nota)
        except Exception as e:  # arquivo corrompido/cancelamento/etc.
            erros.append({"arquivo": os.path.relpath(caminho, pasta), "erro": str(e)})

    saidas = [n for n in notas if n["direcao"] == "saida"]
    entradas = [n for n in notas if n["direcao"] == "entrada"]
    total_saidas = sum(n["vNF"] for n in saidas)
    saidas_pj = sum(n["vNF"] for n in saidas if n["dest_tipo"] == "PJ")
    ufs = {}
    for n in saidas:
        if n["uf_dest"]:
            ufs[n["uf_dest"]] = ufs.get(n["uf_dest"], 0.0) + n["vNF"]
    ncms = {}
    for n in saidas:
        for ncm in n["ncms"]:
            if ncm:
                ncms[ncm] = ncms.get(ncm, 0) + 1
    receita_por_ncm = _agrupar_saidas_por_ncm(saidas)
    por_regime, pct_simples, entradas_cclass = _compras_por_regime_fornecedor(entradas)
    return {
        "qtd_notas": len(notas), "qtd_saidas": len(saidas), "qtd_entradas": len(entradas),
        "total_saidas_vNF": round(total_saidas, 2),
        "total_entradas_vNF": round(sum(n["vNF"] for n in entradas), 2),
        "icms_destacado_saidas": round(sum(n["vICMS"] for n in saidas), 2),
        "mix_b2b_estimado": round(saidas_pj / total_saidas, 4) if total_saidas else None,
        "ufs_destino": {uf: round(v, 2) for uf, v in sorted(ufs.items(), key=lambda kv: -kv[1])},
        "ncms_saida_frequencia": dict(sorted(ncms.items(), key=lambda kv: -kv[1])[:20]),
        "cfops_encontrados": sorted({c for n in notas for c in n["cfops"] if c}),
        # --- classificação oficial (motor/base_oficial.py) ---
        "receita_por_ncm_saidas": receita_por_ncm,
        # pronto para: python3 motor/base_oficial.py classificar <arquivo com esta lista>
        # (sem "cclasstrib": a escolha confirmada é do agente/contador, nunca copiada da nota)
        "itens_para_classificar": [{"descricao": (g["descricoes_exemplo"] or ["NCM " + g["ncm"]])[0],
                                    "ncm": g["ncm"], "valor": g["valor"]} for g in receita_por_ncm],
        # --- créditos (agente levantamento-creditos-ibs-cbs) ---
        "compras_por_regime_fornecedor": por_regime,
        "pct_compras_fornecedor_simples": pct_simples,
        "entradas_por_cclasstrib": entradas_cclass,
        "erros_leitura": erros,
    }


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pasta, cnpj = sys.argv[1], sys.argv[2].replace(".", "").replace("/", "").replace("-", "")
    resumo = consolidar(pasta, cnpj)
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    destino = os.path.join(raiz, "saidas", "resumo_xmls.json")
    if "--saida" in sys.argv and sys.argv.index("--saida") + 1 < len(sys.argv):
        destino = sys.argv[sys.argv.index("--saida") + 1]
    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)
    # na tela, só o resumo (as listas completas ficam no arquivo)
    tela = {k: v for k, v in resumo.items()
            if k not in ("receita_por_ncm_saidas", "itens_para_classificar", "entradas_por_cclasstrib")}
    tela["receita_por_ncm_saidas (top 10)"] = [
        {k: g[k] for k in ("ncm", "valor", "descricoes_exemplo")} for g in resumo["receita_por_ncm_saidas"][:10]]
    tela["ncms_distintos_saida"] = len(resumo["receita_por_ncm_saidas"])
    print(json.dumps(tela, ensure_ascii=False, indent=2))
    print("\nResumo salvo em %s" % destino)


if __name__ == "__main__":
    main()
