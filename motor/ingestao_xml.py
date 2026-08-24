# -*- coding: utf-8 -*-
"""Ingestão de XMLs de NF-e (Agente 1 — parte automatizável).

Uso:
    python3 motor/ingestao_xml.py <pasta_com_xmls> <cnpj_da_empresa>

Varre a pasta, classifica cada NF-e como SAÍDA (emitente = empresa) ou
ENTRADA (destinatário = empresa) e consolida:
- totais por direção (vNF, vProd, vICMS, vIPI, vPIS, vCOFINS)
- receita B2B × B2C (destinatário com CNPJ × CPF) → mix_b2b
- UFs de destino (exposição origem→destino)
- NCMs mais relevantes (para classificar redutores da LC 214)

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
    }
    return nota


def consolidar(pasta, cnpj_empresa):
    notas, erros = [], []
    for nome in sorted(os.listdir(pasta)):
        if not nome.lower().endswith(".xml"):
            continue
        try:
            nota = ler_nfe(os.path.join(pasta, nome), cnpj_empresa)
            if nota:
                notas.append(nota)
        except Exception as e:  # arquivo corrompido/cancelamento/etc.
            erros.append({"arquivo": nome, "erro": str(e)})

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
    return {
        "qtd_notas": len(notas), "qtd_saidas": len(saidas), "qtd_entradas": len(entradas),
        "total_saidas_vNF": round(total_saidas, 2),
        "total_entradas_vNF": round(sum(n["vNF"] for n in entradas), 2),
        "icms_destacado_saidas": round(sum(n["vICMS"] for n in saidas), 2),
        "mix_b2b_estimado": round(saidas_pj / total_saidas, 4) if total_saidas else None,
        "ufs_destino": {uf: round(v, 2) for uf, v in sorted(ufs.items(), key=lambda kv: -kv[1])},
        "ncms_saida_frequencia": dict(sorted(ncms.items(), key=lambda kv: -kv[1])[:20]),
        "cfops_encontrados": sorted({c for n in notas for c in n["cfops"] if c}),
        "erros_leitura": erros,
    }


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    pasta, cnpj = sys.argv[1], sys.argv[2].replace(".", "").replace("/", "").replace("-", "")
    resumo = consolidar(pasta, cnpj)
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    destino = os.path.join(raiz, "saidas", "resumo_xmls.json")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    print("\nResumo salvo em %s" % destino)


if __name__ == "__main__":
    main()
