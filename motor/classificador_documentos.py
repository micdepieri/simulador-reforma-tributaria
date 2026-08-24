# -*- coding: utf-8 -*-
"""Classificador de documentos de empresa (triagem automática).

Uso:
    python3 motor/classificador_documentos.py <pasta_origem> <pasta_empresa> [cnpj_empresa]

Resolve o problema de o cliente jogar tudo (DRE, balanço, folha, PGDAS-D,
XMLs de entrada e saída) numa pasta única, sem organização. Varre
<pasta_origem> recursivamente (ignorando o que já está em documentos/ e
saidas/), classifica cada arquivo e MOVE para a subpasta correta dentro de
<pasta_empresa>/documentos/:

    dre/  balanco_patrimonial/  folha/  pgdas/  xmls/entrada/  xmls/saida/

Classificação:
- XML: parseia como NF-e (schema portalfiscal.inf.br/nfe) e decide
  entrada/saída comparando emitente/destinatário com <cnpj_empresa>. Se não
  for NF-e, tenta heurística de NFS-e (schemas municipais variam — texto
  "nfse"/"issqn" + regex de CNPJ perto de "prestador"/"tomador"). Se
  <cnpj_empresa> não for informado, INFERE pelo CNPJ mais frequente entre
  emitente/destinatário dos próprios XMLs da pasta.
- Demais extensões (PDF/Excel/CSV/imagem/etc.): classifica pelo NOME do
  arquivo contra palavras-chave de cada categoria (sem ler o conteúdo —
  isso é feito pelo agente `ingestao-documentos` depois, com o Read tool).

Tudo que não for reconhecido com confiança fica em <pasta_origem> e entra em
"pendentes_revisao" no relatório — o agente deve abrir esses arquivos
(Read/Grep) para decidir manualmente, ou perguntar ao usuário.

Nunca sobrescreve arquivo existente no destino (acrescenta sufixo _1, _2...
e registra o conflito no relatório).
"""
import json
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET

NS_NFE = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

# pastas que já são organizadas — nunca reclassificar o que já está lá dentro
PASTAS_IGNORADAS = {"documentos", "saidas", "__pycache__"}
ARQUIVOS_IGNORADOS = {".gitkeep", ".ds_store", "perfil_fiscal.json"}

CATEGORIAS = [
    # chave, destino relativo a <pasta_empresa>, tokens (match exato de
    # trecho separado por _/-/./espaço) e frases (match por substring no
    # nome todo junto, sem separadores) — cada uma é suficiente por si só.
    ("dre", "documentos/dre",
     {"dre"},
     {"demonstracaoresultado", "demonstrativoresultado", "resultadoexercicio", "resultadodoexercicio"}),
    ("balanco_patrimonial", "documentos/balanco_patrimonial",
     {"bp", "balanco", "patrimonial"},
     {"balancopatrimonial"}),
    ("folha", "documentos/folha",
     {"folha", "fopag", "holerite", "rh"},
     {"folhapagamento", "folhadepagamento"}),
    ("pgdas", "documentos/pgdas",
     {"pgdas", "das"},
     {"extratosimples", "simplesnacional", "extratopgdas"}),
]


def _normalizar(nome_sem_extensao):
    txt = unicodedata.normalize("NFKD", nome_sem_extensao)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return txt.lower()


def _tokens(nome_normalizado):
    return set(t for t in re.split(r"[^a-z0-9]+", nome_normalizado) if t)


def classificar_por_nome(caminho):
    base = os.path.splitext(os.path.basename(caminho))[0]
    normalizado = _normalizar(base)
    tokens = _tokens(normalizado)
    junto = re.sub(r"[^a-z0-9]", "", normalizado)
    for chave, destino, tokens_categoria, frases_categoria in CATEGORIAS:
        if tokens & tokens_categoria:
            return chave, destino, "nome_contem_token"
        if any(f in junto for f in frases_categoria):
            return chave, destino, "nome_contem_frase"
    return None, None, "nome_nao_reconhecido"


def _texto_xml(root):
    try:
        return ET.tostring(root, encoding="unicode").lower()
    except Exception:
        return ""


def classificar_xml(caminho, cnpj_empresa):
    try:
        root = ET.parse(caminho).getroot()
    except ET.ParseError as e:
        return None, None, "xml_invalido: %s" % e

    inf = root.find(".//nfe:infNFe", NS_NFE)
    if inf is not None:
        emit = inf.find("nfe:emit/nfe:CNPJ", NS_NFE)
        dest = inf.find("nfe:dest/nfe:CNPJ", NS_NFE)
        emit_cnpj = emit.text if emit is not None else None
        dest_cnpj = dest.text if dest is not None else None
        if cnpj_empresa and emit_cnpj == cnpj_empresa:
            return "xml_saida", "documentos/xmls/saida", "nfe_emitente_confere"
        if cnpj_empresa and dest_cnpj == cnpj_empresa:
            return "xml_entrada", "documentos/xmls/entrada", "nfe_destinatario_confere"
        return None, None, "nfe_direcao_indeterminada(emit=%s,dest=%s)" % (emit_cnpj, dest_cnpj)

    conteudo = _texto_xml(root)
    tag_raiz = root.tag.lower()
    if "nfse" in tag_raiz or "nfse" in conteudo[:3000] or "issqn" in conteudo[:3000]:
        prestador = re.search(r"prestador.{0,300}?(\d{14})", conteudo, re.S)
        tomador = re.search(r"tomador.{0,300}?(\d{14})", conteudo, re.S)
        prestador_cnpj = prestador.group(1) if prestador else None
        tomador_cnpj = tomador.group(1) if tomador else None
        if cnpj_empresa and prestador_cnpj == cnpj_empresa:
            return "xml_saida", "documentos/xmls/saida", "nfse_prestador_confere"
        if cnpj_empresa and tomador_cnpj == cnpj_empresa:
            return "xml_entrada", "documentos/xmls/entrada", "nfse_tomador_confere"
        return None, None, "nfse_detectada_direcao_indeterminada"

    return None, None, "xml_nao_reconhecido(tag=%s)" % root.tag


def inferir_cnpj_empresa(caminhos_xml):
    contagem = {}
    for caminho in caminhos_xml:
        try:
            inf = ET.parse(caminho).getroot().find(".//nfe:infNFe", NS_NFE)
        except ET.ParseError:
            continue
        if inf is None:
            continue
        for caminho_tag in ("nfe:emit/nfe:CNPJ", "nfe:dest/nfe:CNPJ"):
            el = inf.find(caminho_tag, NS_NFE)
            if el is not None and el.text:
                contagem[el.text] = contagem.get(el.text, 0) + 1
    if not contagem:
        return None, {}
    cnpj = max(contagem, key=contagem.get)
    return cnpj, contagem


def listar_candidatos(pasta_origem):
    candidatos = []
    for raiz, dirs, arquivos in os.walk(pasta_origem):
        dirs[:] = [d for d in dirs if d not in PASTAS_IGNORADAS and not d.startswith(".")]
        for nome in arquivos:
            if nome.lower() in ARQUIVOS_IGNORADOS or nome.startswith("."):
                continue
            if nome.lower().startswith("_relatorio_classificacao"):
                continue
            candidatos.append(os.path.join(raiz, nome))
    return sorted(candidatos)


def destino_sem_conflito(pasta_destino, nome_arquivo):
    caminho = os.path.join(pasta_destino, nome_arquivo)
    if not os.path.exists(caminho):
        return caminho, False
    base, ext = os.path.splitext(nome_arquivo)
    i = 1
    while True:
        caminho = os.path.join(pasta_destino, "%s_%d%s" % (base, i, ext))
        if not os.path.exists(caminho):
            return caminho, True
        i += 1


def classificar(pasta_origem, pasta_empresa, cnpj_empresa=None, dry_run=False):
    candidatos = listar_candidatos(pasta_origem)
    xmls = [c for c in candidatos if c.lower().endswith(".xml")]

    cnpj_inferido = False
    contagem_cnpj = {}
    if not cnpj_empresa and xmls:
        cnpj_empresa, contagem_cnpj = inferir_cnpj_empresa(xmls)
        cnpj_inferido = cnpj_empresa is not None

    movidos, pendentes, conflitos = [], [], []

    for caminho in candidatos:
        if caminho.lower().endswith(".xml"):
            chave, destino_rel, motivo = classificar_xml(caminho, cnpj_empresa)
        else:
            chave, destino_rel, motivo = classificar_por_nome(caminho)

        if not destino_rel:
            pendentes.append({"arquivo": caminho, "motivo": motivo})
            continue

        pasta_destino = os.path.join(pasta_empresa, destino_rel)
        os.makedirs(pasta_destino, exist_ok=True)
        destino_final, houve_conflito = destino_sem_conflito(pasta_destino, os.path.basename(caminho))
        if houve_conflito:
            conflitos.append({"arquivo": caminho, "destino_gerado": destino_final})

        registro = {"origem": caminho, "destino": destino_final, "categoria": chave, "motivo": motivo}
        movidos.append(registro)
        if not dry_run:
            os.rename(caminho, destino_final)

    relatorio = {
        "pasta_origem": pasta_origem,
        "pasta_empresa": pasta_empresa,
        "cnpj_empresa_usado": cnpj_empresa,
        "cnpj_inferido": cnpj_inferido,
        "contagem_cnpj_nos_xmls": contagem_cnpj,
        "dry_run": dry_run,
        "total_candidatos": len(candidatos),
        "movidos": movidos,
        "conflitos_nome": conflitos,
        "pendentes_revisao": pendentes,
    }
    return relatorio


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    pasta_origem, pasta_empresa = sys.argv[1], sys.argv[2]
    cnpj_empresa = None
    dry_run = "--dry-run" in sys.argv
    for arg in sys.argv[3:]:
        if arg != "--dry-run":
            cnpj_empresa = arg.replace(".", "").replace("/", "").replace("-", "")

    relatorio = classificar(pasta_origem, pasta_empresa, cnpj_empresa, dry_run)

    destino_log = os.path.join(pasta_empresa, "documentos", "_relatorio_classificacao.json")
    os.makedirs(os.path.dirname(destino_log), exist_ok=True)
    with open(destino_log, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, ensure_ascii=False, indent=2)

    print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    print("\nRelatório salvo em %s" % destino_log)
    if relatorio["pendentes_revisao"]:
        print("\nATENÇÃO: %d arquivo(s) não classificado(s) automaticamente — "
              "revisar manualmente." % len(relatorio["pendentes_revisao"]))


if __name__ == "__main__":
    main()
