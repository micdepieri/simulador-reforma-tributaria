# -*- coding: utf-8 -*-
"""Validação cruzada com a Calculadora de Tributos oficial da Receita Federal (Fase 4).

Arquitetura oficial (FAQ do Piloto v1.4, ago/2025):
- NÃO existe API pública online. A integração é com o MÓDULO OFFLINE da
  Calculadora, baixado no portal do piloto (https://piloto-cbs.tributos.gov.br/)
  e executado na infraestrutura local, expondo API REST + Swagger embutido.
- O cálculo é por item e exige: local da operação, data do fato gerador,
  NCM ou NBS, CST × cClassTrib e base de cálculo.
- A Calculadora identifica alíquota, aplica reduções e retorna memória de
  cálculo com base legal — é a FONTE AUTORITATIVA para conferir a classificação
  de redutores (categoria_redutor) do nosso motor.

Papel deste módulo (pilar do projeto): a calculadora oficial VALIDA e ABASTECE
parâmetros; nunca calcula por dentro do motor. Toda simulação continua
reproduzível pela versão do parametros_reforma.json.

Uso:
  python3 motor/validacao_oficial.py --descobrir
      Consulta o Swagger do módulo local e lista os endpoints de cálculo
      disponíveis, para configurar "endpoint_calculo" nos parâmetros.

  python3 motor/validacao_oficial.py <perfil.json> --itens <itens.json>
      Envia cada item (NCM/NBS + base de cálculo + local + data + cClassTrib)
      ao módulo local, compara a alíquota efetiva oficial com a alíquota de
      saída do nosso motor e grava o espelho de divergências em
      saidas/<empresa>/validacao_oficial.{csv,md}.

  Formato de itens.json (montável a partir de saidas/resumo_xmls.json):
  [{"descricao": "...", "ncm": "85171231", "nbs": null, "base_calculo": 1000.0,
    "uf": "SC", "municipio_ibge": "4205407", "data": "2027-01-15",
    "cst": "000", "cclasstrib": "000001"}, ...]

Ressalvas embutidas:
- Simples Nacional ainda em desenvolvimento na Calculadora (FAQ 4.2) —
  a validação cobre o regime regular (Presumido/Real/Simples híbrido).
- Se o módulo local não estiver rodando, o script instrui e sai sem erro
  destrutivo (a simulação principal NUNCA depende desta etapa).
"""
import csv
import json
import os
import sys
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import perfil_fiscal
import ibs_cbs

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _http_json(url, payload=None, timeout=15):
    dados = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=dados,
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def status_modulo(cfg):
    """GET /versao/status — saúde + versões do app e do banco normativo,
    incluindo se estão atualizados frente ao repositório remoto da Receita."""
    try:
        return _http_json(cfg["base_url"] + cfg.get("endpoint_status", "/api/versao/status"))
    except Exception:
        return None


def modulo_disponivel(cfg):
    if status_modulo(cfg) is not None:
        return True
    # fallback: servidor no ar se o endpoint de cálculo devolve qualquer HTTP
    if cfg.get("endpoint_calculo"):
        try:
            _http_json(cfg["base_url"] + cfg["endpoint_calculo"], {})
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            return False
    return False


def dados_abertos(cfg, params, uf_codigo=41, municipio=4106902):
    """Extrai as alíquotas de referência OFICIAIS embarcadas no banco da
    Calculadora (dados abertos) para cada ano da transição, e compara com os
    cenários locais. Alimenta o agente atualizacao-normativa — nunca altera
    parâmetros automaticamente."""
    base = cfg["base_url"] + cfg.get("endpoint_dados_abertos", "/api/calculadora/dados-abertos")
    resultado = {"status": status_modulo(cfg), "aliquotas_referencia": {}}
    for ano in range(2026, 2034):
        data = "%d-01-01" % ano
        linha = {}
        for nome, rota in (("cbs_uniao", "/aliquota-uniao?data=%s" % data),
                           ("ibs_uf", "/aliquota-uf?codigoUf=%d&data=%s" % (uf_codigo, data)),
                           ("ibs_municipio", "/aliquota-municipio?codigoMunicipio=%d&data=%s" % (municipio, data))):
            try:
                linha[nome] = _http_json(base + rota).get("aliquotaReferencia")
            except Exception as e:
                linha[nome] = None
                linha[nome + "_erro"] = str(e)[:80]
        vals = [linha.get("cbs_uniao"), linha.get("ibs_uf"), linha.get("ibs_municipio")]
        linha["total"] = round(sum(v for v in vals if v is not None), 4) if any(v is not None for v in vals) else None
        resultado["aliquotas_referencia"][ano] = linha
    destino = os.path.join(RAIZ, "saidas", "dados_abertos_oficiais.json")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    st = resultado["status"] or {}
    print("Calculadora oficial: app %s · banco %s (%s) · atualizada: %s"
          % (st.get("versaoAplicacaoLocal"), st.get("versaoDbLocal"),
             st.get("dataDb", ""), st.get("dbAtualizada")))
    print("Alíquotas de referência oficiais (UF cód %d, município %d):" % (uf_codigo, municipio))
    for ano, l in resultado["aliquotas_referencia"].items():
        print("  %s: CBS %s%% + IBS UF %s%% + IBS Mun %s%% = %s%%"
              % (ano, l.get("cbs_uniao"), l.get("ibs_uf"), l.get("ibs_municipio"), l.get("total")))
    cen = params["cenarios_aliquota"]["base"]
    print("Cenário base local: %.1f%% — use o agente atualizacao-normativa para propor ajuste se divergente." % (cen["total"] * 100))
    print("Salvo em %s" % destino)
    return resultado


def descobrir(cfg):
    """Lista endpoints do Swagger do módulo local para configurar endpoint_calculo."""
    url = cfg["base_url"] + cfg.get("endpoint_swagger", "/v3/api-docs")
    try:
        spec = _http_json(url)
    except Exception as e:
        print("Módulo offline da Calculadora não encontrado em %s (%s)." % (cfg["base_url"], e))
        print("1) Baixe o pacote offline no portal do piloto: https://piloto-cbs.tributos.gov.br/")
        print("2) Execute-o localmente e confirme a porta.")
        print("3) Ajuste 'calculadora_oficial.base_url' em parametros/parametros_reforma.json.")
        return None
    print("Swagger encontrado (%s). Endpoints:" % spec.get("info", {}).get("title", "sem título"))
    candidatos = []
    for rota, metodos in sorted(spec.get("paths", {}).items()):
        for metodo, det in metodos.items():
            resumo = det.get("summary", "") or det.get("operationId", "")
            print("  %-6s %-50s %s" % (metodo.upper(), rota, resumo))
            texto = (rota + " " + resumo).lower()
            if metodo.lower() == "post" and any(t in texto for t in ("calcul", "tribut", "regime-geral")):
                candidatos.append(rota)
    if candidatos:
        print("\nCandidatos a endpoint de cálculo: %s" % ", ".join(candidatos))
        print("Configure 'calculadora_oficial.endpoint_calculo' e 'habilitada': true nos parâmetros.")
    return spec


def montar_payload(item):
    """Payload conforme o contrato oficial do módulo offline
    (calculadora-oficial/input/entrada-regime-geral.json, v1.3.0):
    POST /api/calculadora/regime-geral
    """
    it = {
        "numero": 1,
        "quantidade": item.get("quantidade", 1),
        "unidade": item.get("unidade", "UN"),
        "cst": item.get("cst", "000"),
        "baseCalculo": item["base_calculo"],
        "cClassTrib": item.get("cclasstrib", "000001"),
    }
    if item.get("ncm"):
        it["ncm"] = item["ncm"]
    if item.get("nbs"):
        it["nbs"] = item["nbs"]
    data = str(item["data"])
    if "T" not in data:
        data += "T12:00:00-03:00"
    return {
        "id": item.get("id", "000000000000000000000000"),
        "versao": "1.0.0",
        "dataHoraEmissao": data,
        "municipio": int(item["municipio_ibge"]),
        "uf": item.get("uf"),
        "itens": [it],
    }


def _extrair_tributos(resposta):
    """Extrai vCBS/vIBS/vIS da resposta oficial (schema v1.3.0).

    A resposta traz os itens em "objetos" e um agregado em "total" — para não
    somar em dobro, percorre apenas "objetos". Valores vêm como strings
    ("vIBS": "0.00"). vIBS já consolida as parcelas UF + Município.
    """
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


def validar(perfil, itens, params, cenario="base"):
    cfg = params["calculadora_oficial"]
    if not cfg.get("habilitada") or not cfg.get("endpoint_calculo"):
        print("Validação oficial desabilitada nos parâmetros (calculadora_oficial).")
        print("Rode --descobrir com o módulo offline local ativo para configurar.")
        return None
    if not modulo_disponivel(cfg):
        print("Módulo offline não responde em %s — validação pulada (a simulação principal não depende desta etapa)." % cfg["base_url"])
        return None

    st = status_modulo(cfg) or {}
    carimbo = {"versao_app": st.get("versaoAplicacaoLocal"), "versao_db": st.get("versaoDbLocal"),
               "db_atualizada": st.get("dbAtualizada")}
    if st and st.get("dbAtualizada") is False:
        print("ATENÇÃO: banco normativo da Calculadora local está DESATUALIZADO frente ao remoto — atualize antes de confiar na validação.")
    tolerancia = cfg.get("tolerancia_divergencia_pp", 0.005)
    resultados = []
    for item in itens:
        # o ano da comparação segue a data do fato gerador do item (cronograma da transição)
        ano_item = max(2026, min(2033, int(str(item["data"])[:4])))
        nosso = ibs_cbs.ibs_cbs_liquido(perfil, ano_item, cenario, params)
        linha = {"descricao": item.get("descricao", ""), "ncm": item.get("ncm") or item.get("nbs"),
                 "base_calculo": item["base_calculo"], "ano": ano_item,
                 "aliq_motor": nosso["aliq_saida"]}
        try:
            resp = _http_json(cfg["base_url"] + cfg["endpoint_calculo"], montar_payload(item))
            linha["resposta_bruta"] = resp
            trib = _extrair_tributos(resp)
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
            linha["erro"] = "HTTP %s %s — %s" % (e.code, e.reason, corpo or "(sem corpo; verifique NCM/cClassTrib contra as tabelas vigentes)")
        except Exception as e:
            linha["erro"] = str(e)
        resultados.append(linha)

    slug = perfil["nome"].lower().replace(" ", "_")
    pasta = os.path.join(RAIZ, "saidas", slug)
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, "validacao_oficial.json"), "w", encoding="utf-8") as f:
        json.dump({"calculadora": carimbo, "parametros_versao": params.get("versao"),
                   "itens": resultados}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(pasta, "validacao_oficial.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["descricao", "ncm_nbs", "base_calculo", "aliq_motor", "aliq_oficial", "divergencia_pp", "divergente", "erro"])
        for r in resultados:
            w.writerow([r.get("descricao"), r.get("ncm"), r.get("base_calculo"), r.get("aliq_motor"),
                        r.get("aliq_oficial"), r.get("divergencia_pp"), r.get("divergente"), r.get("erro", "")])
    divergentes = [r for r in resultados if r.get("divergente")]
    print("Validação oficial: %d itens, %d divergentes (tolerância %.2f p.p.)."
          % (len(resultados), len(divergentes), 100 * tolerancia))
    for r in divergentes:
        print("  DIVERGE %s (NCM %s): motor %.2f%% × oficial %.2f%%"
              % (r["descricao"], r["ncm"], 100 * r["aliq_motor"], 100 * r["aliq_oficial"]))
    print("Espelho salvo em %s" % pasta)
    return resultados


def main():
    params = perfil_fiscal.carregar_parametros()
    if "--descobrir" in sys.argv:
        descobrir(params["calculadora_oficial"])
        return
    if "--dados-abertos" in sys.argv:
        dados_abertos(params["calculadora_oficial"], params)
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
    validar(perfil, itens, params)


if __name__ == "__main__":
    main()
