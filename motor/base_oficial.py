# -*- coding: utf-8 -*-
"""Banco normativo OFICIAL da Calculadora de Tributos da Receita Federal (RTC),
consultado localmente — sem Java, sem Docker, sem servidor.

Desde a Release 15 (out/2026) a Receita publica a Calculadora como código aberto:
  - github.com/ReceitaFederal/calculadora-rtc-regime-regular  (contém o banco
    normativo inteiro em scripts SQL Flyway: B0001 + V0002…V00NN)
  - github.com/ReceitaFederal/calculadora-rtc-simples-nacional (código do Simples;
    as tabelas do Simples vêm das migrações V0047/V0049/V0050 do repo acima)

Este módulo baixa os scripts SQL do repositório oficial, monta o mesmo SQLite que
a Calculadora usa (calculadora-pro.db) e responde, item a item:
  NCM / NBS / item da LC 116  →  cClassTrib  →  CST, % de redução por tributo,
  anexo da LC 214, fundamentação legal, indicadores de crédito, tpRBSN (Simples).

Papel no projeto (mesmo pilar do validacao_oficial.py): a fonte oficial
CLASSIFICA e ABASTECE o perfil fiscal; o cálculo continua no motor, com as
alíquotas de parametros_reforma.json. Toda saída carimba a versão do banco
(ex.: V0059) — classificações antigas continuam reproduzíveis.

Uso:
  python3 motor/base_oficial.py montar [--fonte <pasta flyway/sql | arquivo .zip>]
  python3 motor/base_oficial.py versao
  python3 motor/base_oficial.py novidades            # compara com o GitHub
  python3 motor/base_oficial.py ncm 10063021 [--data 2027-01-01]
  python3 motor/base_oficial.py nbs 122011200
  python3 motor/base_oficial.py lc116 4.03
  python3 motor/base_oficial.py cclasstrib 200028
  python3 motor/base_oficial.py atividades-simples
  python3 motor/base_oficial.py sem-codigo           # reduções que só se acham pela descrição
  python3 motor/base_oficial.py classificar <itens.json> [--saida mix.json]
      [--qualificacao "conselho profissional;..."]   (atores que a EMPRESA atende)
      [--aceitar-propostas]   (estimativa rápida: aplica reduções sem conferir o anexo — sai carimbado)

  itens.json: [{"descricao": "...", "ncm": "10063021", "valor": 1000.0}, …]
  (cada item traz ncm OU nbs OU lc116; "valor" = receita do item no período;
   opcional "cclasstrib" = classificação CONFIRMADA por quem conferiu o anexo)

Regras de escolha da classificação (prudência — nunca superestimar benefício):
  1. Candidatos = cClassTrib vinculados ao código na data (tabelas NCM_APLICAVEL,
     NBS_APLICAVEL, CLASSIF_NBS_INDOP_LC), descontadas as exceções oficiais.
  2. Vínculo pelo código NÃO basta quando o vínculo oficial traz o texto de um item
     de anexo da LC 214 (ex.: NCM 30049099 só tem −60% se for "substituto de enxerto
     ósseo"): a redução vira PROPOSTA A CONFIRMAR e o mix usa tributação integral até
     alguém comparar a descrição do produto com o texto oficial e gravar "cclasstrib"
     no item. Essa comparação é julgamento — papel do agente/contador, não do código.
  3. Classificação que exige ator ADQUIRENTE (governo, entidade imune…) fica fora da
     operação comum; a que exige ator FORNECEDOR (ex.: profissional com conselho, art.
     127) só vale se a empresa declarar a qualificação (qualificacoes_fornecedor).
  4. Entre candidatos automáticos: vínculo de código mais específico; empate → MENOR
     redução, marcada "ambigua".
  5. Nenhum vínculo: tributação integral (cClassTrib 000001).
  6. cClassTrib escolhido que não está vinculado ao código é rejeitado (é o erro REG-011
     da Calculadora) e o item fica com tributação integral.
  7. CSTs sem modelagem no motor (alíquota fixa, monofásico, diferimento, suspensão,
     ajustes…) não entram no mix — vão para "nao_modelados".
"""
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import urllib.request
import zipfile
from datetime import date, datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA_BASE = os.path.join(RAIZ, "calculadora-oficial", "base")
ARQ_DB = os.path.join(PASTA_BASE, "calculadora-pro.db")
ARQ_META = os.path.join(PASTA_BASE, "meta.json")

REPO = "ReceitaFederal/calculadora-rtc-regime-regular"
URL_ZIP = "https://codeload.github.com/%s/zip/refs/heads/main" % REPO
URL_API = "https://api.github.com/repos/%s" % REPO
USER_AGENT = "simulador-reforma-tributaria"   # genérico, sem dado do usuário

TRIBUTOS = {2: "cbs", 3: "ibs_uf", 4: "ibs_mun"}   # TBTO_ID (1 = Imposto Seletivo)
# CSTs que o motor sabe modelar como "fração de redução da alíquota de saída"
CST_SEM_REDUCAO = {"000"}
CST_COM_PERCENTUAL = {"200", "011", "515"}
CST_REDUCAO_TOTAL = {"100", "400", "410", "500", "600"}   # imunidade, isenção, alíquota zero


# ----------------------------------------------------------------------------
# Montagem do banco
# ----------------------------------------------------------------------------

def _http(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _num_versao(nome):
    m = re.match(r"[BV](\d+)__", nome)
    return int(m.group(1)) if m else None


def _scripts_de_pasta(pasta_sql):
    crit = os.path.join(pasta_sql, "criacao")
    manu = os.path.join(pasta_sql, "manutencao")
    migr = [os.path.join(crit, f) for f in os.listdir(crit) if _num_versao(f) is not None]
    migr += [os.path.join(manu, f) for f in os.listdir(manu) if _num_versao(f) is not None]
    migr.sort(key=lambda p: _num_versao(os.path.basename(p)))
    return ([os.path.join(crit, "beforeMigrate.sql")] + migr
            + [os.path.join(crit, "afterMigrate.sql")])


def _extrair_sql_do_zip(dados_zip, destino):
    """Extrai SOMENTE flyway/sql/{criacao,manutencao}/*.sql (sem seguir caminhos
    do zip — evita zip-slip). Retorna a pasta 'sql' montada em destino."""
    pasta_sql = os.path.join(destino, "sql")
    for sub in ("criacao", "manutencao"):
        os.makedirs(os.path.join(pasta_sql, sub), exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(dados_zip)) as z:
        for info in z.infolist():
            partes = info.filename.replace("\\", "/").split("/")
            if len(partes) >= 4 and partes[-4:-2] == ["flyway", "sql"] and partes[-1].endswith(".sql"):
                sub, nome = partes[-2], os.path.basename(partes[-1])
                if sub in ("criacao", "manutencao") and re.match(r"^[\w.-]+\.sql$", nome):
                    with z.open(info) as src, open(os.path.join(pasta_sql, sub, nome), "wb") as dst:
                        shutil.copyfileobj(src, dst)
    return pasta_sql


def _autorizador(acao, *_):
    # O SQL vem de fonte externa: nada de ATTACH (criaria/escreveria arquivos fora daqui).
    if acao in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def montar(fonte=None, silencioso=False):
    """Monta calculadora-oficial/base/calculadora-pro.db.

    fonte: None (baixa do GitHub), pasta 'flyway/sql' local, ou arquivo .zip do repo.
    Aplica beforeMigrate → B0001 → V* em ordem → afterMigrate, cada migração numa
    transação. A checagem de chave estrangeira é feita UMA vez no fim (o Flyway valida
    no commit; executando script a script com FK imediata, sete migrações oficiais falham
    por ordem de INSERT dentro do próprio script).
    """
    log = (lambda *a: None) if silencioso else print
    tmp = tempfile.mkdtemp(prefix="base_oficial_")
    commit = None
    try:
        if fonte is None:
            log("Baixando scripts SQL de github.com/%s ..." % REPO)
            pasta_sql = _extrair_sql_do_zip(_http(URL_ZIP, timeout=180), tmp)
            try:
                commit = json.loads(_http(URL_API + "/commits/main", timeout=20)).get("sha")
            except Exception:
                commit = None
        elif os.path.isdir(fonte):
            pasta_sql = fonte
        else:
            with open(fonte, "rb") as f:
                pasta_sql = _extrair_sql_do_zip(f.read(), tmp)

        scripts = _scripts_de_pasta(pasta_sql)
        os.makedirs(PASTA_BASE, exist_ok=True)
        provisorio = ARQ_DB + ".novo"
        if os.path.exists(provisorio):
            os.remove(provisorio)
        con = sqlite3.connect(provisorio, isolation_level=None)
        con.set_authorizer(_autorizador)
        for caminho in scripts:
            with open(caminho, encoding="utf-8-sig") as f:
                sql = f.read()
            sql = re.sub(r"(?im)^\s*PRAGMA\s+foreign_keys\s*=\s*\w+\s*;", "", sql)
            nome = os.path.basename(caminho)
            con.execute("PRAGMA foreign_keys = OFF")
            try:
                if nome in ("beforeMigrate.sql", "afterMigrate.sql"):
                    con.executescript(sql)
                else:
                    con.executescript("BEGIN;\n" + sql + "\nCOMMIT;")
            except Exception as e:
                try:
                    con.execute("ROLLBACK")
                except Exception:
                    pass
                con.close()
                raise RuntimeError("Falha ao aplicar %s: %s" % (nome, e))
        violacoes = con.execute("PRAGMA foreign_key_check").fetchall()
        integridade = con.execute("PRAGMA integrity_check").fetchone()[0]
        versao_db, data_db = con.execute(
            "SELECT VRBD_VERSAO_BASE_DADO, VRBD_DATA FROM VERSAO_BASE_DADO "
            "ORDER BY CAST(SUBSTR(VRBD_VERSAO_BASE_DADO, 2) AS INTEGER) DESC LIMIT 1").fetchone()
        con.close()
        if violacoes or integridade != "ok":
            raise RuntimeError("Banco montado com problemas: %d violações de FK, integridade=%s"
                               % (len(violacoes), integridade))
        os.replace(provisorio, ARQ_DB)
        meta = {
            "versao_banco": versao_db, "data_banco": str(data_db)[:10],
            "scripts_aplicados": len(scripts), "commit_github": commit,
            "fonte": "github.com/%s" % REPO if fonte is None else os.path.abspath(fonte),
            "montado_em": datetime.now().isoformat(timespec="seconds"),
        }
        with open(ARQ_META, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        log("Banco oficial %s (%s) montado: %d scripts, integridade ok → %s"
            % (versao_db, meta["data_banco"], len(scripts), os.path.relpath(ARQ_DB, RAIZ)))
        return meta
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def meta():
    if not os.path.exists(ARQ_META):
        return None
    with open(ARQ_META, encoding="utf-8") as f:
        return json.load(f)


def conectar():
    if not os.path.exists(ARQ_DB):
        raise FileNotFoundError(
            "Banco oficial não montado. Rode: python3 motor/base_oficial.py montar "
            "(precisa de internet uma vez; ~15 MB do GitHub da Receita).")
    con = sqlite3.connect("file:%s?mode=ro" % ARQ_DB.replace("\\", "/"), uri=True)
    con.row_factory = sqlite3.Row
    return con


def novidades():
    """Lista migrações publicadas no GitHub mais novas que o banco local."""
    local = meta() or {}
    num_local = _num_versao((local.get("versao_banco") or "V0") + "__") or 0
    itens = json.loads(_http(URL_API + "/contents/flyway/sql/manutencao", timeout=20))
    remotas = sorted((n for n in (i.get("name", "") for i in itens) if _num_versao(n)),
                     key=_num_versao)
    novas = [n for n in remotas if _num_versao(n) > num_local]
    return {"versao_local": local.get("versao_banco"),
            "versao_remota": "V%04d" % _num_versao(remotas[-1]) if remotas else None,
            "novas_migracoes": novas}


# ----------------------------------------------------------------------------
# Consultas
# ----------------------------------------------------------------------------

def _data(d):
    return (d or date.today().isoformat())[:10]


VIGENTE = "({p}_INICIO_VIGENCIA <= :data AND ({p}_FIM_VIGENCIA IS NULL OR {p}_FIM_VIGENCIA >= :data))"


def _vig(prefixo):
    return VIGENTE.format(p=prefixo)


def detalhar_cclasstrib(con, cltr_id, data=None):
    """Ficha completa de uma classificação (por CLTR_ID)."""
    d = {"data": _data(data)}
    r = con.execute(
        "SELECT ct.*, st.SITR_CD, st.SITR_DESCRICAO, "
        "  (SELECT MIN(TRST_TBTO_ID) FROM TRIBUTO_SITUACAO_TRIBUTARIA t WHERE t.TRST_SITR_ID = ct.CLTR_SITR_ID) AS TBTO "
        "FROM CLASSIFICACAO_TRIBUTARIA ct JOIN SITUACAO_TRIBUTARIA st ON st.SITR_ID = ct.CLTR_SITR_ID "
        "WHERE ct.CLTR_ID = ?", (cltr_id,)).fetchone()
    reducoes = {nome: 0.0 for nome in TRIBUTOS.values()}
    for p in con.execute("SELECT PERE_TBTO_ID, PERE_VALOR FROM PERCENTUAL_REDUCAO "
                         "WHERE PERE_CLTR_ID = :id AND " + _vig("PERE"), dict(d, id=cltr_id)):
        if p["PERE_TBTO_ID"] in TRIBUTOS:
            reducoes[TRIBUTOS[p["PERE_TBTO_ID"]]] = round(p["PERE_VALOR"] / 100.0, 6)
    fund = [dict(texto=f["FDLG_TEXTO_CURTO"])
            for f in con.execute(
                "SELECT fl.FDLG_TEXTO_CURTO FROM FUNDAMENTACAO_CLASSIFICACAO fc "
                "JOIN FUNDAMENTACAO_LEGAL fl ON fl.FDLG_ID = fc.FDCL_FDLG_ID "
                "WHERE fc.FDCL_CLTR_ID = :id AND " + _vig("fc.FDCL"), dict(d, id=cltr_id))]
    atores = [dict(ator=a["ATOR_DESCRICAO"], papel=a["ATCL_IN_PAPEL"])
              for a in con.execute(
                  "SELECT a.ATOR_DESCRICAO, ac.ATCL_IN_PAPEL FROM ATOR_CLASSIFICACAO ac "
                  "JOIN ATOR a ON a.ATOR_ID = ac.ATCL_ATOR_ID "
                  "WHERE ac.ATCL_CLTR_ID = :id AND " + _vig("ac.ATCL"), dict(d, id=cltr_id))]
    cst = r["SITR_CD"]
    if cst in CST_SEM_REDUCAO:
        modelagem, red = "integral", {"cbs": 0.0, "ibs": 0.0}
    elif cst in CST_REDUCAO_TOTAL:
        modelagem, red = "reducao_total", {"cbs": 1.0, "ibs": 1.0}
    elif cst in CST_COM_PERCENTUAL:
        modelagem = "reducao_percentual"
        red = {"cbs": reducoes["cbs"], "ibs": reducoes["ibs_uf"]}
    else:
        modelagem, red = "nao_modelado", None
    return {
        "cclasstrib": r["CLTR_CD"],
        "descricao": r["CLTR_DESCRICAO"],
        "cst": cst, "cst_descricao": r["SITR_DESCRICAO"],
        "tributo": "imposto_seletivo" if r["TBTO"] == 1 else "ibs_cbs",
        "tipo_aliquota": r["CLTR_TIPO_ALIQUOTA"],
        "anexo_lc214": r["CLTR_ANEXO"],
        "reducao_por_tributo": reducoes,
        "reducao_motor": red,           # o que o simulador aplica (None = fora do motor)
        "modelagem": modelagem,
        "ibs_uf_mun_divergem": reducoes["ibs_uf"] != reducoes["ibs_mun"],
        "credito": {
            "apropriacao_adquirente_cbs": r["CLTR_IN_APROPRIACAO_CREDITOS_ADQUIRENTES_CBS"],
            "apropriacao_adquirente_ibs": r["CLTR_IN_APROPRIACAO_CREDITOS_ADQUIRENTES_IBS"],
            "credito_presumido_fornecedor": r["CLTR_IN_CREDITO_PRESUMIDO_FORNECEDOR"],
            "credito_presumido_adquirente": r["CLTR_IN_CREDITO_PRESUMIDO_ADQUIRENTE"],
            "credito_operacao_antecedente": r["CLTR_CREDITO_OPERACAO_ANTECEDENTE"],
        },
        "tp_rbsn": r["CLTR_TPRBSN"],     # Tipo de Receita Bruta do Simples (NT 2026.005)
        "fundamentacao": ["LC 214/2025, %s" % f["texto"] for f in fund if f["texto"]],
        "atores_exigidos": atores,      # vazio = operação comum
    }


def _id_cclasstrib(con, codigo, data):
    r = con.execute(
        "SELECT ct.CLTR_ID FROM CLASSIFICACAO_TRIBUTARIA ct "
        "WHERE ct.CLTR_CD = :cd AND " + _vig("ct.CLTR") + " AND EXISTS ("
        " SELECT 1 FROM TRIBUTO_SITUACAO_TRIBUTARIA t WHERE t.TRST_SITR_ID = ct.CLTR_SITR_ID AND t.TRST_TBTO_ID = 2)",
        {"cd": codigo, "data": _data(data)}).fetchone()
    return r["CLTR_ID"] if r else None


def consultar_cclasstrib(codigo, data=None):
    con = conectar()
    cid = _id_cclasstrib(con, codigo, data)
    return detalhar_cclasstrib(con, cid, data) if cid else None


def _candidatos(con, tipo, cod, data):
    """Vínculos oficiais do código na data → (lista de (CLTR_ID, nº de dígitos que casou,
    texto do item de anexo ou None), código existe na tabela oficial?)."""
    p = {"cod": cod, "data": _data(data)}
    if tipo == "ncm":
        brutos = con.execute(
            "SELECT na.NCMA_CLTR_ID AS cid, LENGTH(na.NCMA_NCM_CD) AS n, ax.ANXO_NUMERO AS anexo, "
            "  ax.ANXO_NUMERO_ITEM AS item, ax.ANXO_TEXTO_ITEM AS texto, "
            "  EXISTS (SELECT 1 FROM EXCECAO_NCM_APLICAVEL e WHERE e.ENCM_NCMA_ID = na.NCMA_ID AND "
            + _vig("e.ENCM") + ") AS tem_excecao, "
            "  EXISTS (SELECT 1 FROM EXCECAO_NCM_APLICAVEL e WHERE e.ENCM_NCMA_ID = na.NCMA_ID "
            "    AND :cod LIKE e.ENCM_NCM_CD || '%' AND " + _vig("e.ENCM") + ") AS excecao_cobre "
            "FROM NCM_APLICAVEL na LEFT JOIN ANEXO ax ON ax.ANXO_ID = na.NCMA_ANXO_ID "
            "WHERE :cod LIKE na.NCMA_NCM_CD || '%' AND " + _vig("na.NCMA"), p).fetchall()
        # Regra oficial (NcmAplicavelService.criticar): por classificação, A = há vínculo
        # cobrindo o NCM; E = alguma exceção vigente cobre o NCM; S = há vínculo cobrindo
        # SEM nenhuma exceção vigente. Aceita quando A e (não E ou S).
        por_cid = {}
        for r in brutos:
            por_cid.setdefault(r["cid"], []).append(r)
        rows = []
        for cid, rs in por_cid.items():
            e = any(r["excecao_cobre"] for r in rs)
            s = any(not r["tem_excecao"] for r in rs)
            if not e or s:
                rows.extend(r for r in rs if not r["excecao_cobre"])
        existe = con.execute("SELECT 1 FROM NCM WHERE NCM_CD = :cod AND " + _vig("NCM"), p).fetchone()
    elif tipo == "nbs":
        rows = con.execute(
            "SELECT na.NBSA_CLTR_ID AS cid, LENGTH(na.NBSA_NBS_CD) AS n, ax.ANXO_NUMERO AS anexo, "
            "  ax.ANXO_NUMERO_ITEM AS item, ax.ANXO_TEXTO_ITEM AS texto "
            "FROM NBS_APLICAVEL na LEFT JOIN ANEXO ax ON ax.ANXO_ID = na.NBSA_ANXO_ID "
            "WHERE :cod LIKE na.NBSA_NBS_CD || '%' AND " + _vig("na.NBSA"), p).fetchall()
        existe = con.execute("SELECT 1 FROM NBS WHERE NBS_CD = :cod AND " + _vig("NBS"), p).fetchone()
    else:  # lc116 → tabela oficial LC 116 × NBS × cClassTrib (sem texto de anexo)
        rows = con.execute(
            "SELECT DISTINCT CNIL_CLTR_ID AS cid, 0 AS n, NULL AS anexo, NULL AS item, NULL AS texto "
            "FROM CLASSIF_NBS_INDOP_LC WHERE CNIL_LSLC_CD = :cod AND " + _vig("CNIL"), p).fetchall()
        existe = con.execute("SELECT 1 FROM LISTA_SERVICOS_LC_116 WHERE LSLC_CD = :cod AND " + _vig("LSLC"),
                             p).fetchone()
    return rows, existe is not None


def _sem_vinculo_de_codigo(con, cclasstrib, tipo, data):
    """True se o cClassTrib existe (CBS/IBS, vigente) e NÃO tem nenhuma tabela de códigos
    do tipo do item — caso em que a Calculadora não critica o código (aceita qualquer um)."""
    cid = _id_cclasstrib(con, cclasstrib, data)
    if cid is None:
        return False
    # nomenclatura exigida pela classificação: 'NCM' (bens), 'NBS' (serviços),
    # 'NBS ou NCM' ou 'Não possui' — item de serviço não usa cClassTrib de bem e vice-versa
    nomencl = (con.execute("SELECT CLTR_NOMENCLATURA FROM CLASSIFICACAO_TRIBUTARIA WHERE CLTR_ID = ?",
                           (cid,)).fetchone()[0] or "").upper()
    aceita_ncm = "NCM" in nomencl or "POSSUI" in nomencl
    aceita_nbs = "NBS" in nomencl or "POSSUI" in nomencl
    if (tipo == "ncm" and not aceita_ncm) or (tipo in ("nbs", "lc116") and not aceita_nbs):
        return False
    p = {"id": cid, "data": _data(data)}
    if tipo == "ncm":
        sql = "SELECT 1 FROM NCM_APLICAVEL WHERE NCMA_CLTR_ID = :id AND " + _vig("NCMA")
    elif tipo == "nbs":
        sql = "SELECT 1 FROM NBS_APLICAVEL WHERE NBSA_CLTR_ID = :id AND " + _vig("NBSA")
    else:
        sql = ("SELECT 1 FROM NBS_APLICAVEL WHERE NBSA_CLTR_ID = :id AND " + _vig("NBSA") +
               " UNION SELECT 1 FROM CLASSIF_NBS_INDOP_LC WHERE CNIL_CLTR_ID = :id AND " + _vig("CNIL"))
    return con.execute(sql, p).fetchone() is None


def tratamentos_sem_codigo(data=None):
    """Reduções/isenções oficiais SEM tabela de NCM/NBS/LC 116 — só se identificam pela
    descrição da operação ou do produto (ex.: medicamentos registrados na Anvisa,
    absorventes, bares e restaurantes, livros, exportação). O agente deve conferir o
    catálogo do cliente contra esta lista, porque a busca por código não os encontra."""
    con = conectar()
    p = {"data": _data(data)}
    ids = [r["CLTR_ID"] for r in con.execute(
        "SELECT ct.CLTR_ID FROM CLASSIFICACAO_TRIBUTARIA ct JOIN SITUACAO_TRIBUTARIA st ON st.SITR_ID = ct.CLTR_SITR_ID "
        "WHERE " + _vig("ct.CLTR") + " AND st.SITR_CD IN ('200','011','515','100','400','410','500','600') "
        "AND EXISTS (SELECT 1 FROM TRIBUTO_SITUACAO_TRIBUTARIA t WHERE t.TRST_SITR_ID = ct.CLTR_SITR_ID AND t.TRST_TBTO_ID = 2) "
        "AND NOT EXISTS (SELECT 1 FROM NCM_APLICAVEL n WHERE n.NCMA_CLTR_ID = ct.CLTR_ID AND " + _vig("n.NCMA") + ") "
        "AND NOT EXISTS (SELECT 1 FROM NBS_APLICAVEL n WHERE n.NBSA_CLTR_ID = ct.CLTR_ID AND " + _vig("n.NBSA") + ") "
        "AND NOT EXISTS (SELECT 1 FROM CLASSIF_NBS_INDOP_LC n WHERE n.CNIL_CLTR_ID = ct.CLTR_ID AND " + _vig("n.CNIL") + ") "
        "ORDER BY ct.CLTR_CD", p)]
    saida = []
    for cid in ids:
        f = detalhar_cclasstrib(con, cid, data)
        if f["reducao_motor"] is None:
            continue
        saida.append({"cclasstrib": f["cclasstrib"], "cst": f["cst"], "descricao": f["descricao"],
                      "reducao_motor": f["reducao_motor"], "fundamentacao": f["fundamentacao"],
                      "operacao_comum": not any(a["papel"] == "Adquirente" for a in f["atores_exigidos"]),
                      "atores_exigidos": ["%s (%s)" % (a["ator"], a["papel"]) for a in f["atores_exigidos"]]})
    return saida


def _normaliza_lc116(item):
    s = str(item).strip()
    m = re.match(r"^(\d{1,2})\.?(\d{2})", s.replace(",", "."))
    return "%d.%s" % (int(m.group(1)), m.group(2)) if m else s


def _peso_reducao(f):
    r = f["reducao_motor"] or {"cbs": 9, "ibs": 9}
    return r["cbs"] + r["ibs"]


def _atende_fornecedor(ficha, qualificacoes):
    """A empresa (fornecedora) declarou atender o ator exigido? Casamento por trecho
    da descrição oficial do ator (ex.: 'conselho profissional')."""
    exigidos = [a["ator"].lower() for a in ficha["atores_exigidos"] if a["papel"] == "Fornecedor"]
    quals = [q.lower() for q in (qualificacoes or [])]
    return any(q in ator for ator in exigidos for q in quals)


def _fichas_candidatas(con, tipo, cod, data):
    rows, existe = _candidatos(con, tipo, cod, data)
    agreg = {}
    for r in rows:
        a = agreg.setdefault(r["cid"], {"n": 0, "textos": [], "sem_condicao": False})
        a["n"] = max(a["n"], r["n"])
        if r["texto"]:
            t = {"anexo": r["anexo"], "item": r["item"], "texto": r["texto"]}
            if t not in a["textos"]:
                a["textos"].append(t)
        else:
            a["sem_condicao"] = True      # vínculo pelo código, sem descrição de anexo
    fichas = []
    for cid, a in agreg.items():
        f = detalhar_cclasstrib(con, cid, data)
        f["_especificidade"] = a["n"]
        f["_itens_anexo"] = a["textos"]
        # depende da descrição do produto quando TODO vínculo do código traz texto de anexo
        f["_condicionado"] = bool(a["textos"]) and not a["sem_condicao"]
        fichas.append(f)
    return fichas, existe


def classificar_item(item, data=None, con=None, qualificacoes=None, aceitar_propostas=False):
    """Classifica um item pela base oficial.

    item: {"descricao", "ncm"|"nbs"|"lc116", "valor", opcional "cclasstrib", "qualificacoes"}

    Resultado:
    - "aplicada": o cClassTrib que entra no mix_redutores (o que o motor simula);
    - "propostas_a_confirmar": reduções cujo vínculo oficial depende da DESCRIÇÃO do
      produto num anexo da LC 214 (ex.: NCM 30049099 só tem −60% se for "substituto de
      enxerto ósseo"). Não entram no mix até alguém confirmar — gravando "cclasstrib"
      no item — porque o código da NCM sozinho não prova o enquadramento.
    """
    con = con or conectar()
    if item.get("ncm"):
        tipo, cod = "ncm", re.sub(r"\D", "", str(item["ncm"]))
    elif item.get("nbs"):
        tipo, cod = "nbs", re.sub(r"\D", "", str(item["nbs"]))
    elif item.get("lc116"):
        tipo, cod = "lc116", _normaliza_lc116(item["lc116"])
    else:
        return {"descricao": item.get("descricao"), "erro": "item sem ncm, nbs ou lc116"}

    fichas, existe = _fichas_candidatas(con, tipo, cod, data)
    quals = qualificacoes if qualificacoes is not None else item.get("qualificacoes")
    seletivo = any(f["tributo"] == "imposto_seletivo" for f in fichas)
    ibs_cbs = [f for f in fichas if f["tributo"] == "ibs_cbs"]
    integral = detalhar_cclasstrib(con, _id_cclasstrib(con, "000001", data), data)
    integral.update(_especificidade=0, _itens_anexo=[], _condicionado=False)
    alertas, pendentes_ator = [], []

    # elegibilidade por ator (quem compra / quem vende)
    elegiveis = []
    for f in ibs_cbs:
        papeis = {a["papel"] for a in f["atores_exigidos"]}
        if "Adquirente" in papeis:
            continue                      # depende de QUEM COMPRA: fora da operação comum
        if "Fornecedor" in papeis and not _atende_fornecedor(f, quals):
            pendentes_ator.append(f)      # depende da EMPRESA: só com qualificação declarada
            continue
        elegiveis.append(f)

    escolha = str(item.get("cclasstrib") or "").strip()
    propostas = []
    if escolha:
        # escolha explícita (confirmada pelo agente/contador): valida o vínculo oficial
        vinculadas = {f["cclasstrib"]: f for f in ibs_cbs}
        if escolha == "000001":
            aplicada, situacao = integral, "confirmada"
        elif escolha in vinculadas or _sem_vinculo_de_codigo(con, escolha, tipo, data):
            if escolha in vinculadas:
                aplicada = vinculadas[escolha]
            else:
                # classificação sem tabela de códigos (ex.: 200032 medicamentos Anvisa,
                # 200047 bares e restaurantes): a Calculadora aceita sem crítica de NCM —
                # o enquadramento é pela descrição/qualificação, confirmado por quem escolheu
                aplicada = detalhar_cclasstrib(con, _id_cclasstrib(con, escolha, data), data)
                aplicada.update(_especificidade=0, _itens_anexo=[], _condicionado=False)
                alertas.append("cClassTrib %s não tem tabela de códigos vinculada — enquadramento pela "
                               "descrição/qualificação da operação; guarde a evidência." % escolha)
            situacao = "confirmada"
            if any(a["papel"] == "Adquirente" for a in aplicada["atores_exigidos"]) or (
                    any(a["papel"] == "Fornecedor" for a in aplicada["atores_exigidos"])
                    and not _atende_fornecedor(aplicada, quals)):
                alertas.append("cClassTrib %s exige ator específico (%s) — conferir se a operação atende."
                               % (escolha, "; ".join("%s (%s)" % (a["ator"], a["papel"])
                                                     for a in aplicada["atores_exigidos"])))
        else:
            aplicada, situacao = integral, "escolha_invalida"
            alertas.append("cClassTrib %s NÃO está vinculado a %s %s na tabela oficial (a Calculadora "
                           "rejeitaria: REG-011) — aplicada tributação integral." % (escolha, tipo.upper(), cod))
    else:
        automaticas = [f for f in elegiveis if not f["_condicionado"]]
        condicionadas = [f for f in elegiveis if f["_condicionado"]]
        # 1) vínculo mais específico do código; 2) entre empates, a MENOR redução (prudência)
        if automaticas:
            top = max(f["_especificidade"] for f in automaticas)
            pool = sorted((f for f in automaticas if f["_especificidade"] == top), key=_peso_reducao)
            aplicada = pool[0]
            situacao = "ambigua" if len({_peso_reducao(f) for f in pool}) > 1 else "automatica"
        else:
            aplicada = integral
            situacao = "sem_vinculo" if not ibs_cbs else ("a_confirmar" if condicionadas else "so_com_ator_especifico")
        propostas = sorted((f for f in condicionadas if _peso_reducao(f) > _peso_reducao(aplicada)),
                           key=lambda f: (-f["_especificidade"], _peso_reducao(f)))
        if propostas and aceitar_propostas:
            aplicada, situacao = propostas[0], "proposta_aceita_sem_conferencia"
            propostas = propostas[1:]
            alertas.append("Proposta %s aplicada SEM conferência da descrição do anexo (--aceitar-propostas) "
                           "— estimativa, confirmar antes de entregar." % aplicada["cclasstrib"])
        elif propostas:
            alertas.append("Redução possível conforme a DESCRIÇÃO do produto (anexo da LC 214) — compare com o "
                           "texto oficial em 'propostas_a_confirmar' e grave 'cclasstrib' no item para aplicar. "
                           "Até lá o mix usa tributação integral.")

    confianca = {"confirmada": "confirmada", "automatica": "alta", "sem_vinculo": "alta",
                 "ambigua": "media", "a_confirmar": "pendente", "proposta_aceita_sem_conferencia": "baixa",
                 "so_com_ator_especifico": "pendente", "escolha_invalida": "baixa"}[situacao]
    if not existe:
        confianca = "baixa"
        alertas.append("%s %s não consta como vigente na tabela oficial em %s — conferir o código "
                       "(a Calculadora rejeitaria o item)." % (tipo.upper(), cod, _data(data)))
    if situacao == "ambigua":
        alertas.append("Mais de um cClassTrib igualmente específico; adotada a MENOR redução (prudência).")
    for f in pendentes_ator:
        exig = "; ".join(a["ator"] for a in f["atores_exigidos"] if a["papel"] == "Fornecedor")
        alertas.append("Redução possível SE a empresa for: %s → cClassTrib %s (%s). Declare em "
                       "qualificacoes_fornecedor para aplicar." % (exig, f["cclasstrib"], f["descricao"]))
    if seletivo:
        alertas.append("Item sujeito ao IMPOSTO SELETIVO — não modelado no motor; análise à parte.")
    if aplicada["modelagem"] == "nao_modelado":
        alertas.append("CST %s (%s) não é redução simples de alíquota — fora do mix, tratar como regime específico."
                       % (aplicada["cst"], aplicada["cst_descricao"]))
    if aplicada.get("ibs_uf_mun_divergem"):
        alertas.append("Redução de IBS estadual e municipal diferem; o motor usa a estadual.")

    def resumo(f):
        return {"cclasstrib": f["cclasstrib"], "descricao": f["descricao"], "reducao_motor": f["reducao_motor"],
                "itens_anexo": f["_itens_anexo"], "fundamentacao": f["fundamentacao"],
                "atores_exigidos": ["%s (%s)" % (a["ator"], a["papel"]) for a in f["atores_exigidos"]]}

    return {
        "descricao": item.get("descricao"), "tipo_codigo": tipo, "codigo": cod,
        "valor": float(item.get("valor") or 0.0),
        "cclasstrib": aplicada["cclasstrib"], "cst": aplicada["cst"],
        "classificacao": aplicada["descricao"], "anexo_lc214": aplicada["anexo_lc214"],
        "itens_anexo": aplicada["_itens_anexo"],
        "reducao_motor": aplicada["reducao_motor"], "modelagem": aplicada["modelagem"],
        "fundamentacao": list(dict.fromkeys(aplicada["fundamentacao"])),
        "credito": aplicada["credito"], "tp_rbsn": aplicada["tp_rbsn"],
        "confianca": confianca, "situacao": situacao, "imposto_seletivo": seletivo,
        "propostas_a_confirmar": [resumo(f) for f in propostas],
        "alternativas": [resumo(f) for f in ibs_cbs
                         if f["cclasstrib"] != aplicada["cclasstrib"] and f not in propostas],
        "alertas": alertas,
    }


def classificar(itens, data=None, qualificacoes=None, aceitar_propostas=False):
    """Classifica uma lista de itens e devolve o mix de redutores para o perfil.

    mix_redutores: fatias da receita classificada com a redução APLICADA de cada uma
    (inclusive tributação integral, redução 0). Quando o perfil traz mix_redutores, a
    redução de saída do motor é a média ponderada do mix (motor/ibs_cbs.py:
    reducoes_saida); a fração fora do mix (itens não modelados) segue a
    categoria_redutor do perfil. Supõe que os itens representam o perfil de receita.
    """
    con = conectar()
    linhas = [classificar_item(i, data, con, qualificacoes, aceitar_propostas) for i in itens]
    validas = [l for l in linhas if "erro" not in l]
    total = sum(l["valor"] for l in validas)
    grupos, nao_modelados, a_confirmar = {}, [], []
    for l in validas:
        if l["modelagem"] == "nao_modelado" or l["imposto_seletivo"]:
            nao_modelados.append({"descricao": l["descricao"], "codigo": l["codigo"],
                                  "cclasstrib": l["cclasstrib"], "valor": l["valor"],
                                  "motivo": "imposto_seletivo" if l["imposto_seletivo"] else "cst_" + l["cst"]})
            if l["modelagem"] == "nao_modelado":
                continue
        if l["propostas_a_confirmar"]:
            melhor = l["propostas_a_confirmar"][0]
            a_confirmar.append({"descricao": l["descricao"], "codigo": l["codigo"], "valor": l["valor"],
                                "cclasstrib_proposto": melhor["cclasstrib"],
                                "reducao_proposta": melhor["reducao_motor"]})
        red = l["reducao_motor"]
        if not red:
            continue
        # itens de tributação integral (redução 0) ENTRAM no mix: senão a receita
        # deles cairia no residual e herdaria a categoria_redutor do perfil
        g = grupos.setdefault(l["cclasstrib"], {"cclasstrib": l["cclasstrib"],
                                                "descricao": l["classificacao"],
                                                "reducao_cbs": red["cbs"], "reducao_ibs": red["ibs"],
                                                "valor": 0.0})
        g["valor"] += l["valor"]
    m = meta() or {}
    mix = []
    for g in sorted(grupos.values(), key=lambda g: -g["valor"]):
        g["participacao"] = round(g["valor"] / total, 6) if total else 0.0
        g["fonte"] = "base_oficial RFB %s" % m.get("versao_banco", "?")
        g["valor"] = round(g["valor"], 2)
        mix.append(g)
    soma_nm = sum(n["valor"] for n in nao_modelados)
    soma_ac = sum(a["valor"] for a in a_confirmar)
    pendentes = [l["descricao"] or l["codigo"] for l in validas if l["confianca"] in ("pendente", "baixa")]
    return {
        "versao_banco": m.get("versao_banco"), "data_referencia": _data(data),
        "propostas_aceitas_sem_conferencia": bool(aceitar_propostas),
        "receita_classificada": round(total, 2),
        "mix_redutores": mix,
        "participacao_nao_modelada": round(soma_nm / total, 6) if total else 0.0,
        "nao_modelados": nao_modelados,
        "participacao_a_confirmar": round(soma_ac / total, 6) if total else 0.0,
        "reducoes_a_confirmar": a_confirmar,
        "itens_pendentes": pendentes,
        "itens_com_erro": [l for l in linhas if "erro" in l],
        "itens": linhas,
    }


def atividades_simples(data=None):
    con = conectar()
    return [dict(r) for r in con.execute(
        "SELECT ATSN_CATIVSN AS cativsn, ATSN_DESCRICAO AS descricao, ATSN_ROTULO_CURTO AS anexo, "
        "ATSN_ANEXO_SEM_FATOR_R AS anexo_sem_fator_r, ATSN_ANEXO_COM_FATOR_R AS anexo_com_fator_r, "
        "ATSN_IN_NAO_TRIBUTAVEL AS nao_tributavel FROM ATIVIDADE_SIMPLES_NACIONAL "
        "WHERE " + _vig("ATSN") + " ORDER BY ATSN_ORDEM", {"data": _data(data)})]


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def _opcao(nome, padrao=None):
    if nome in sys.argv:
        i = sys.argv.index(nome)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return padrao


def _imprimir(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd, data = sys.argv[1], _opcao("--data")
    quals = [q for q in (_opcao("--qualificacao") or "").split(";") if q.strip()] or None
    if cmd == "montar":
        montar(_opcao("--fonte"))
    elif cmd == "versao":
        _imprimir(meta() or {"erro": "banco não montado — rode: python3 motor/base_oficial.py montar"})
    elif cmd == "novidades":
        try:
            n = novidades()
        except Exception as e:
            print("Não foi possível consultar o GitHub da Receita (%s)." % e)
            return
        if n["novas_migracoes"]:
            print("Banco local %s; GitHub da Receita já está em %s. Novas migrações:"
                  % (n["versao_local"], n["versao_remota"]))
            for nome in n["novas_migracoes"]:
                print("  - " + nome)
            print("Rode 'python3 motor/base_oficial.py montar' e peça ao agente atualizacao-normativa "
                  "para avaliar o impacto nos parâmetros.")
        else:
            print("Banco oficial local (%s) está em dia com o GitHub da Receita." % n["versao_local"])
    elif cmd in ("ncm", "nbs", "lc116") and len(sys.argv) > 2:
        _imprimir(classificar_item({cmd: sys.argv[2], "descricao": "%s %s" % (cmd, sys.argv[2])},
                                   data, qualificacoes=quals))
    elif cmd == "cclasstrib" and len(sys.argv) > 2:
        _imprimir(consultar_cclasstrib(sys.argv[2], data) or {"erro": "cClassTrib não encontrado/vigente"})
    elif cmd == "atividades-simples":
        _imprimir(atividades_simples(data))
    elif cmd == "sem-codigo":
        _imprimir(tratamentos_sem_codigo(data))
    elif cmd == "classificar" and len(sys.argv) > 2:
        with open(sys.argv[2], encoding="utf-8") as f:
            itens = json.load(f)
        res = classificar(itens, data, quals, "--aceitar-propostas" in sys.argv)
        saida = _opcao("--saida")
        if saida:
            with open(saida, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=2)
            print("Classificação salva em %s" % saida)
        print("Banco oficial %s · receita classificada R$ %.2f" % (res["versao_banco"], res["receita_classificada"]))
        for g in res["mix_redutores"]:
            print("  %5.1f%% da receita → %s (CBS −%.0f%%, IBS −%.0f%%) %s"
                  % (100 * g["participacao"], g["cclasstrib"], 100 * g["reducao_cbs"], 100 * g["reducao_ibs"],
                     g["descricao"][:60]))
        if res["reducoes_a_confirmar"]:
            print("  %.1f%% da receita com REDUÇÃO A CONFIRMAR pela descrição do anexo (hoje simulada como integral):"
                  % (100 * res["participacao_a_confirmar"]))
            for a in res["reducoes_a_confirmar"]:
                print("    - %s (%s) → proposta %s" % (a["descricao"], a["codigo"], a["cclasstrib_proposto"]))
        if res["nao_modelados"]:
            print("  %.1f%% da receita em tratamento não modelado (regime específico/IS) — análise à parte."
                  % (100 * res["participacao_nao_modelada"]))
        if res["propostas_aceitas_sem_conferencia"]:
            print("  ATENÇÃO: --aceitar-propostas ligado — reduções aplicadas sem conferir o texto do anexo.")
        if res["itens_com_erro"]:
            print("  Itens com erro: %d (sem ncm/nbs/lc116)" % len(res["itens_com_erro"]))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
