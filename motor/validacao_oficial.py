# -*- coding: utf-8 -*-
"""Validação cruzada com a Calculadora de Tributos oficial da Receita Federal.

Arquitetura (Release 15, out/2026): a Calculadora é CÓDIGO ABERTO no GitHub e roda
localmente como API REST (Java 21 / Spring Boot), cada módulo na sua porta:
  - regime regular (CBS/IBS/IS):  github.com/ReceitaFederal/calculadora-rtc-regime-regular
    → http://localhost:8080/api  (contrato 1.6.0)
  - Simples Nacional:             github.com/ReceitaFederal/calculadora-rtc-simples-nacional
    → http://localhost:8082/api
O banco normativo (NCM/NBS → cClassTrib → reduções) também é consultável SEM a API,
direto em SQLite, por motor/base_oficial.py — é ele que classifica os itens.

Papel deste módulo (pilar do projeto): a Calculadora oficial VALIDA; nunca calcula
por dentro do motor. Toda simulação continua reproduzível pela versão do
parametros_reforma.json.

Mudanças do contrato 1.6.0 tratadas aqui:
  - "dhFatoGerador" substitui "dataHoraEmissao" (obsoleto);
  - a Receita APAGOU as alíquotas de referência de CBS/IBS posteriores a 2026 (migração
    V0053 — "não definidas em lei"): a partir de 2027 o item EXIGE "aliquotasNominais"
    e o resultado sai como CALCULO_SIMULADO. Enviamos as alíquotas do NOSSO cenário —
    então a validação confere a CLASSIFICAÇÃO (vínculo NCM/NBS × cClassTrib, redução,
    regras de cálculo), não a alíquota de referência, que nenhuma fonte oficial fixou;
  - endpoint de observabilidade: erro por item (ex.: REG-011 NCM não vinculada) sem
    derrubar os demais.

Uso:
  python3 motor/validacao_oficial.py --descobrir
  python3 motor/validacao_oficial.py --dados-abertos      (usa a API se estiver no ar;
                                                            senão, o banco local de base_oficial.py)
  python3 motor/validacao_oficial.py <perfil.json> --itens <itens.json> [--cenario base]
  python3 motor/validacao_oficial.py <perfil.json> --simples [--anos 2027,2029,2033]
                                                   [--cativsn 07] [--cenario base]

  itens.json (montável a partir de saidas/resumo_xmls.json → itens_para_classificar):
  [{"descricao": "...", "ncm": "85171231", "base_calculo": 1000.0,
    "uf": "SC", "municipio_ibge": "4205407", "data": "2027-01-15",
    "cst": "000", "cclasstrib": "000001"}, ...]
  cst/cclasstrib são opcionais: sem eles, o item é classificado por base_oficial.py.

Se a API não estiver rodando, o script instrui e sai sem erro destrutivo (a simulação
principal NUNCA depende desta etapa).
"""
import csv
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import perfil_fiscal
import ibs_cbs
import regime_atual

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _opcao(nome, padrao=None):
    if nome in sys.argv:
        i = sys.argv.index(nome)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return padrao


def _http_json(url, payload=None, timeout=15):
    dados = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=dados,
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def status_modulo(cfg, base_url=None):
    """GET /versao/status — saúde + versões do app e do banco normativo
    (perfil offline), incluindo se estão atualizados frente ao remoto da Receita."""
    try:
        return _http_json((base_url or cfg["base_url"]) + cfg.get("endpoint_status", "/api/versao/status"))
    except Exception:
        return None


def modulo_disponivel(cfg, base_url=None, endpoint=None):
    if status_modulo(cfg, base_url) is not None:
        return True
    endpoint = endpoint or cfg.get("endpoint_calculo")
    if endpoint:
        try:
            _http_json((base_url or cfg["base_url"]) + endpoint, {})
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            return False
    return False


def _instrucoes_instalacao(cfg, modulo="regime regular"):
    print("Calculadora oficial (%s) não responde. Para subir localmente (Java 21):" % modulo)
    print("  Windows:      calculadora-oficial\\instalar-github.ps1   e depois   calculadora-oficial\\executar.ps1")
    print("  Linux/macOS:  ./calculadora-oficial/instalar-github.sh   e depois   ./calculadora-oficial/executar.sh")
    print("Fontes: %s" % ", ".join((cfg.get("fonte_codigo") or {}).values()))


# ----------------------------------------------------------------------------
# Alíquotas de referência (dados abertos)
# ----------------------------------------------------------------------------

def dados_abertos(cfg, params, uf_codigo=41, municipio=4106902):
    """Alíquotas de referência OFICIAIS por ano da transição × cenários locais.

    Desde a V0053 o banco oficial só traz 2026 (ano-teste): de 2027 em diante a API
    responde 404 — não há alíquota de referência definida em lei. Isso é registrado
    explicitamente, para que nenhum relatório chame um cenário local de "oficial".
    Alimenta o agente atualizacao-normativa — nunca altera parâmetros."""
    resultado = {"fonte": None, "status": None, "aliquotas_referencia": {}}
    if modulo_disponivel(cfg):
        resultado["fonte"] = "api_local"
        resultado["status"] = status_modulo(cfg)
        base = cfg["base_url"] + cfg.get("endpoint_dados_abertos", "/api/calculadora/dados-abertos")
        for ano in range(2026, 2034):
            data = "%d-01-01" % ano
            linha = {}
            for nome, rota in (("cbs_uniao", "/aliquota-uniao?data=%s" % data),
                               ("ibs_uf", "/aliquota-uf?codigoUf=%d&data=%s" % (uf_codigo, data)),
                               ("ibs_municipio", "/aliquota-municipio?codigoMunicipio=%d&data=%s" % (municipio, data))):
                try:
                    linha[nome] = _http_json(base + rota).get("aliquotaReferencia")
                except urllib.error.HTTPError as e:
                    linha[nome] = None
                    if e.code == 404:
                        linha["nao_definida_em_lei"] = True
                except Exception as e:
                    linha[nome] = None
                    linha[nome + "_erro"] = str(e)[:80]
            resultado["aliquotas_referencia"][ano] = linha
    else:
        # sem API: lê direto do banco oficial montado por base_oficial.py
        try:
            import base_oficial
            con = base_oficial.conectar()
        except Exception as e:
            print("Nem a API local nem o banco oficial estão disponíveis (%s)." % e)
            print("Rode: python3 motor/base_oficial.py montar")
            return None
        resultado["fonte"] = "banco_local %s" % (base_oficial.meta() or {}).get("versao_banco")
        nomes = {2: "cbs_uniao", 3: "ibs_uf", 4: "ibs_municipio"}
        for ano in range(2026, 2034):
            data = "%d-01-01" % ano
            linha = {}
            for r in con.execute("SELECT ALRE_TBTO_ID, ALRE_VALOR FROM ALIQUOTA_REFERENCIA WHERE "
                                 "ALRE_INICIO_VIGENCIA <= ? AND (ALRE_FIM_VIGENCIA IS NULL OR ALRE_FIM_VIGENCIA >= ?)",
                                 (data, data)):
                if r["ALRE_TBTO_ID"] in nomes:
                    linha[nomes[r["ALRE_TBTO_ID"]]] = r["ALRE_VALOR"]
            if not linha:
                linha = {"cbs_uniao": None, "ibs_uf": None, "ibs_municipio": None, "nao_definida_em_lei": True}
            resultado["aliquotas_referencia"][ano] = linha
    for linha in resultado["aliquotas_referencia"].values():
        vals = [linha.get(k) for k in ("cbs_uniao", "ibs_uf", "ibs_municipio")]
        linha["total"] = round(sum(v for v in vals if v is not None), 4) if any(v is not None for v in vals) else None

    destino = os.path.join(RAIZ, "saidas", "dados_abertos_oficiais.json")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print("Fonte: %s" % resultado["fonte"])
    print("Alíquotas de referência oficiais (%%, UF cód %d, município %d):" % (uf_codigo, municipio))
    for ano, l in resultado["aliquotas_referencia"].items():
        if l.get("nao_definida_em_lei") and l.get("total") is None:
            print("  %s: sem alíquota oficial (não definida em lei — retirada do banco na V0053)" % ano)
        else:
            print("  %s: CBS %s + IBS UF %s + IBS Mun %s = %s"
                  % (ano, l.get("cbs_uniao"), l.get("ibs_uf"), l.get("ibs_municipio"), l.get("total")))
    for nome, cen in params["cenarios_aliquota"].items():
        print("Cenário local %-12s %.2f%% — %s" % (nome + ":", cen["total"] * 100, cen.get("fonte", "estimativa")))
    print("Salvo em %s" % destino)
    return resultado


def descobrir(cfg):
    """Lista endpoints do Swagger dos módulos locais."""
    for rotulo, base in (("regime regular", cfg["base_url"]), ("Simples Nacional", cfg.get("base_url_simples"))):
        if not base:
            continue
        url = base + cfg.get("endpoint_swagger", "/api/api-docs")
        try:
            spec = _http_json(url)
        except Exception as e:
            print("[%s] não encontrado em %s (%s)." % (rotulo, base, e))
            continue
        print("[%s] Swagger %s:" % (rotulo, spec.get("info", {}).get("title", "sem título")))
        for rota, metodos in sorted(spec.get("paths", {}).items()):
            for metodo, det in metodos.items():
                print("  %-6s %-60s %s" % (metodo.upper(), rota, det.get("summary", "") or det.get("operationId", "")))


# ----------------------------------------------------------------------------
# Regime regular
# ----------------------------------------------------------------------------

def aliquotas_nominais(ano, cenario, params):
    """aliquotasNominais (pontos percentuais) do nosso cenário para o ano, como a API
    exige a partir de 2027. O IBS é repartido entre UF e município pela fração
    calculadora_oficial.fracao_ibs_estadual_nominal — a soma é o que se compara."""
    cbs, ibs, _ = ibs_cbs.aliquotas_ano(ano, cenario, params)
    co = params["calculadora_oficial"]
    frac_uf = (co.get("fracao_ibs_estadual_nominal_por_ano") or {}).get(
        str(ano), co.get("fracao_ibs_estadual_nominal", 1.0))
    return {"cbs": round(cbs * 100, 4),
            "ibsEstadual": round(ibs * frac_uf * 100, 4),
            "ibsMunicipal": round(ibs * (1 - frac_uf) * 100, 4)}


def _classificar(item, data):
    """Completa cst/cClassTrib pelo banco oficial quando o item não traz."""
    try:
        import base_oficial
        return base_oficial.classificar_item(
            {"descricao": item.get("descricao"), "ncm": item.get("ncm"), "nbs": item.get("nbs"),
             "lc116": item.get("lc116"), "cclasstrib": item.get("cclasstrib")}, data)
    except Exception:
        return None


def montar_payload(item, params, cenario="base"):
    """Payload do contrato 1.6.0: POST /api/calculadora/observabilidade/regime-geral."""
    data = str(item["data"])[:10]
    ano = int(data[:4])
    it = {
        "numero": 1,
        "quantidade": item.get("quantidade", 1),
        "unidade": item.get("unidade", "UN"),
        "cst": item["cst"],
        "baseCalculo": item["base_calculo"],
        "cClassTrib": item["cclasstrib"],
    }
    if item.get("ncm"):
        it["ncm"] = item["ncm"]
    if item.get("nbs"):
        it["nbs"] = item["nbs"]
    if ano >= 2027:   # obrigatório a partir de 2027; proibido antes (docs/exemplos.md oficial)
        it["aliquotasNominais"] = aliquotas_nominais(ano, cenario, params)
    return {
        "id": item.get("id", "000000000000000000000000"),
        "versao": "1.0.0",
        "dhFatoGerador": data + "T12:00:00-03:00",
        "municipio": int(item["municipio_ibge"]),
        "uf": item.get("uf"),
        "itens": [it],
    }


def _extrair_tributos(resposta):
    """vCBS/vIBS/vIS dos objetos da resposta (strings → float). Percorre só "objetos"
    para não somar o agregado "total" em dobro; vIBS já consolida UF + município."""
    achados = {}
    raiz = resposta.get("objetos", resposta)

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def caminhar(no):
        if isinstance(no, dict):
            for k, v in no.items():
                kl = k.lower()
                if kl in ("vcbs", "vibs", "vis"):
                    n = _num(v)
                    if n is not None:
                        chave = {"vcbs": "cbs", "vibs": "ibs", "vis": "is"}[kl]
                        achados[chave] = achados.get(chave, 0.0) + n
                else:
                    caminhar(v)
        elif isinstance(no, list):
            for x in no:
                caminhar(x)

    caminhar(raiz)
    return achados


def _estado_e_erros(resposta):
    objetos = resposta.get("objetos") or []
    if not objetos:
        return None, []
    o = objetos[0]
    erros = ["%s %s: %s" % (e.get("code", ""), e.get("title", ""), e.get("detail", ""))
             for e in (o.get("erros") or [])]
    return o.get("estadoItem"), erros


def validar(perfil, itens, params, cenario="base"):
    cfg = params["calculadora_oficial"]
    if not cfg.get("habilitada"):
        print("Validação oficial desabilitada nos parâmetros (calculadora_oficial.habilitada).")
        return None
    endpoint = cfg.get("endpoint_calculo_observabilidade") or cfg["endpoint_calculo"]
    if not modulo_disponivel(cfg, endpoint=endpoint):
        _instrucoes_instalacao(cfg)
        print("Validação pulada (a simulação principal não depende desta etapa).")
        return None

    st = status_modulo(cfg) or {}
    carimbo = {"versao_app": st.get("versaoAplicacaoLocal"), "versao_db": st.get("versaoDbLocal"),
               "db_atualizada": st.get("dbAtualizada"), "cenario_aliquotas_nominais": cenario}
    if st and st.get("dbAtualizada") is False:
        print("ATENÇÃO: banco normativo da Calculadora local está DESATUALIZADO frente ao remoto — "
              "atualize antes de confiar na validação.")
    tolerancia = cfg.get("tolerancia_divergencia_pp", 0.005)
    resultados = []
    for item in itens:
        item = dict(item)
        data = str(item["data"])[:10]
        ano_item = max(2026, min(2033, int(data[:4])))
        cbs, ibs, _ = ibs_cbs.aliquotas_ano(ano_item, cenario, params)
        classif = None
        if not (item.get("cst") and item.get("cclasstrib")):
            classif = _classificar(item, data)
            if classif and "erro" not in classif:
                item["cst"], item["cclasstrib"] = classif["cst"], classif["cclasstrib"]
            else:
                item.setdefault("cst", "000")
                item.setdefault("cclasstrib", "000001")
        # alíquota que o MOTOR atribui ao item: a do cClassTrib do item, se modelável;
        # senão a redução média do perfil
        red = (classif or {}).get("reducao_motor")
        if red:
            aliq_motor = cbs * (1 - red["cbs"]) + ibs * (1 - red["ibs"])
        else:
            aliq_motor = ibs_cbs.aliquota_saida(cbs, ibs, perfil, params)
        linha = {"descricao": item.get("descricao", ""), "ncm_nbs": item.get("ncm") or item.get("nbs"),
                 "cst": item["cst"], "cclasstrib": item["cclasstrib"],
                 "classificacao_por": "base_oficial" if classif else "item",
                 "base_calculo": item["base_calculo"], "ano": ano_item, "aliq_motor": round(aliq_motor, 6)}
        try:
            resp = _http_json(cfg["base_url"] + endpoint, montar_payload(item, params, cenario))
            linha["resposta_bruta"] = resp
            linha["estado_item"], linha["erros_oficiais"] = _estado_e_erros(resp)
            trib = _extrair_tributos(resp)
            if trib and not linha["erros_oficiais"]:
                total = trib.get("cbs", 0.0) + trib.get("ibs", 0.0)
                linha["aliq_oficial"] = round(total / item["base_calculo"], 6) if item["base_calculo"] else None
                if linha["aliq_oficial"] is not None:
                    linha["divergencia_pp"] = round(linha["aliq_oficial"] - linha["aliq_motor"], 6)
                    linha["divergente"] = abs(linha["divergencia_pp"]) > tolerancia
        except urllib.error.HTTPError as e:
            corpo = ""
            try:
                corpo = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            linha["erro"] = "HTTP %s %s — %s" % (e.code, e.reason, corpo or "(sem corpo)")
        except Exception as e:
            linha["erro"] = str(e)
        resultados.append(linha)

    pasta = _pasta_saida(perfil)
    with open(os.path.join(pasta, "validacao_oficial.json"), "w", encoding="utf-8") as f:
        json.dump({"calculadora": carimbo, "parametros_versao": params.get("versao"),
                   "itens": resultados}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(pasta, "validacao_oficial.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["descricao", "ncm_nbs", "cst", "cclasstrib", "ano", "base_calculo", "aliq_motor",
                    "aliq_oficial", "divergencia_pp", "divergente", "estado_item", "erros_oficiais", "erro"])
        for r in resultados:
            w.writerow([r.get("descricao"), r.get("ncm_nbs"), r.get("cst"), r.get("cclasstrib"), r.get("ano"),
                        r.get("base_calculo"), r.get("aliq_motor"), r.get("aliq_oficial"), r.get("divergencia_pp"),
                        r.get("divergente"), r.get("estado_item"), " | ".join(r.get("erros_oficiais") or []),
                        r.get("erro", "")])
    divergentes = [r for r in resultados if r.get("divergente")]
    rejeitados = [r for r in resultados if r.get("erros_oficiais") or r.get("erro")]
    print("Validação oficial: %d itens, %d divergentes (tolerância %.2f p.p.), %d rejeitados pela Calculadora."
          % (len(resultados), len(divergentes), 100 * tolerancia, len(rejeitados)))
    for r in divergentes:
        print("  DIVERGE %s (%s, cClassTrib %s): motor %.2f%% × oficial %.2f%%"
              % (r["descricao"], r["ncm_nbs"], r["cclasstrib"], 100 * r["aliq_motor"], 100 * r["aliq_oficial"]))
    for r in rejeitados:
        print("  REJEITADO %s (%s): %s" % (r["descricao"], r["ncm_nbs"],
                                            "; ".join(r.get("erros_oficiais") or []) or r.get("erro")))
    print("Espelho salvo em %s" % pasta)
    return resultados


# ----------------------------------------------------------------------------
# Simples Nacional
# ----------------------------------------------------------------------------

def validar_simples(perfil, params, cenario="base", anos=(2027, 2029, 2033), cativsn=None):
    """Confere, na Calculadora oficial do Simples, o IBS/CBS que a nota do optante
    destaca (= crédito do adquirente) com os percentuais pCBSSN/pIBSSN que o motor
    estima (ibs_cbs.aliquotas_simples_ibs_cbs). A Calculadora NÃO calcula a alíquota
    efetiva (é do PGDAS-D); ela valida a operação (atividade × documento × cClassTrib,
    tipo de receita bruta) e o valor destacado. Não é validação da alíquota efetiva."""
    cfg = params["calculadora_oficial"]
    sn = cfg.get("simples") or {}
    base = cfg.get("base_url_simples")
    endpoint = cfg.get("endpoint_calculo_simples")
    if perfil["regime_atual"] != "simples":
        print("Perfil não é do Simples Nacional — modo --simples não se aplica.")
        return None
    carga = regime_atual.carga_simples(perfil, params)
    if "erro" in carga:
        print("Não foi possível calcular o DAS do perfil: %s" % carga["erro"])
        return None
    anexo = carga["memoria"]["anexo_aplicado"]
    cativsn = cativsn or (sn.get("cativsn_por_anexo") or {}).get(anexo)
    if not cativsn:
        print("Informe --cativsn: o anexo %s não tem código de atividade padrão nos parâmetros "
              "(consulte: python3 motor/base_oficial.py atividades-simples)." % anexo)
        return None
    if not base or not endpoint or not modulo_disponivel(cfg, base, endpoint):
        _instrucoes_instalacao(cfg, "Simples Nacional")
        print("Validação do Simples pulada (a simulação principal não depende desta etapa).")
        return None
    tpdoc = (sn.get("tpdoc_por_atividade") or {}).get(perfil["atividade"], "55")
    base_calc = 1000.0
    resultados = []
    for ano in anos:
        p_cbs, p_ibs = ibs_cbs.aliquotas_simples_ibs_cbs(carga, ano, params)
        payload = {"id": "000000000000000000000000", "versao": "1.0.0", "data": "%d-03-15" % ano,
                   "tpDoc": tpdoc, "CRT": "1",
                   "itens": [{"numero": 1, "cAtivSN": cativsn, "cClassTrib": sn.get("cclasstrib_padrao", "000001"),
                              "baseCalculo": "%.2f" % base_calc,
                              "pIBSSN": "%.4f" % (p_ibs * 100), "pCBSSN": "%.4f" % (p_cbs * 100)}]}
        linha = {"ano": ano, "anexo": anexo, "cativsn": cativsn, "tpdoc": tpdoc,
                 "pCBSSN_motor": round(p_cbs * 100, 4), "pIBSSN_motor": round(p_ibs * 100, 4),
                 "credito_adquirente_motor": round(base_calc * (p_cbs + p_ibs), 2)}
        try:
            resp = _http_json(base + endpoint, payload)
            linha["resposta_bruta"] = resp
            linha["estado_item"], linha["erros_oficiais"] = _estado_e_erros(resp)
            trib = ((resp.get("objetos") or [{}])[0].get("tribCalc") or {})
            v_cbs, v_ibs = float(trib.get("vCBSSN") or 0), float(trib.get("vIBSSN") or 0)
            linha["credito_adquirente_oficial"] = round(v_cbs + v_ibs, 2)
            linha["tp_rbsn"] = trib.get("tpRBSNDescricao")
            linha["divergencia_reais"] = round(linha["credito_adquirente_oficial"] - linha["credito_adquirente_motor"], 2)
        except urllib.error.HTTPError as e:
            try:
                corpo = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                corpo = ""
            linha["erro"] = "HTTP %s %s — %s" % (e.code, e.reason, corpo)
        except Exception as e:
            linha["erro"] = str(e)
        resultados.append(linha)
    pasta = _pasta_saida(perfil)
    with open(os.path.join(pasta, "validacao_oficial_simples.json"), "w", encoding="utf-8") as f:
        json.dump({"parametros_versao": params.get("versao"), "cenario": cenario,
                   "status": status_modulo(cfg, base), "anos": resultados}, f, ensure_ascii=False, indent=2)
    print("Validação Simples (anexo %s, cAtivSN %s, tpDoc %s), base de cálculo R$ 1.000,00:" % (anexo, cativsn, tpdoc))
    for r in resultados:
        if r.get("erro") or r.get("erros_oficiais"):
            print("  %d: REJEITADO — %s" % (r["ano"], r.get("erro") or "; ".join(r["erros_oficiais"])))
        else:
            print("  %d: pCBSSN %.2f%% + pIBSSN %.2f%% → crédito do adquirente motor R$ %.2f × oficial R$ %.2f"
                  % (r["ano"], r["pCBSSN_motor"], r["pIBSSN_motor"], r["credito_adquirente_motor"],
                     r["credito_adquirente_oficial"]))
    print("Salvo em %s" % pasta)
    return resultados


def _pasta_saida(perfil):
    slug = perfil["nome"].lower().replace(" ", "_")
    pasta = os.path.join(RAIZ, "saidas", slug)
    os.makedirs(pasta, exist_ok=True)
    return pasta


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    params = perfil_fiscal.carregar_parametros()
    cenario = _opcao("--cenario", "base")
    if "--descobrir" in sys.argv:
        descobrir(params["calculadora_oficial"])
        return
    if "--dados-abertos" in sys.argv:
        dados_abertos(params["calculadora_oficial"], params)
        return
    if len(sys.argv) >= 3 and sys.argv[2] == "--simples":
        perfil = perfil_fiscal.carregar_perfil(sys.argv[1])
        anos = tuple(int(a) for a in _opcao("--anos", "2027,2029,2033").split(","))
        validar_simples(perfil, params, cenario, anos, _opcao("--cativsn"))
        return
    if len(sys.argv) < 4 or sys.argv[2] != "--itens":
        print(__doc__)
        sys.exit(1)
    perfil = perfil_fiscal.carregar_perfil(sys.argv[1])
    try:
        with open(sys.argv[3], "r", encoding="utf-8") as f:
            itens = json.load(f)
        assert isinstance(itens, list) and itens, "lista vazia"
    except Exception as e:
        print("Arquivo de itens inválido (%s): %s" % (sys.argv[3], e))
        print("Formato esperado: lista JSON de itens — veja o docstring deste módulo.")
        sys.exit(1)
    validar(perfil, itens, params, cenario)


if __name__ == "__main__":
    main()
