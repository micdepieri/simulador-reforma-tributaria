---
name: iniciar
description: Inicia, via entrevista, o processo de análise da Reforma Tributária para uma empresa nova — pergunta o nome da empresa, cria a pasta em empresas/, coleta os documentos (recebendo-os diretamente ou orientando onde salvá-los), confirma o que chegou, roda a classificação/extração e a simulação, e avisa sobre inconsistências ou documentos faltantes ao longo do processo. Use quando o usuário digitar /iniciar, ou pedir para começar/iniciar uma nova análise de reforma tributária para uma empresa/cliente.
---

# /iniciar — Início do processo de análise da Reforma Tributária

Este comando conduz a ENTREVISTA inicial com o usuário. É conversa de mão
dupla — pergunte, espere a resposta, só avance quando tiver o que precisa.
Não pule etapas para "ser rápido"; a qualidade da análise final depende de
cada uma delas.

## Fluxo

### 1. Nome da empresa

Pergunte a razão social ou nome fantasia da empresa. Aproveite e pergunte
também (ajuda os passos seguintes, mas não é bloqueante):
- CNPJ (melhora a classificação automática dos XMLs — sem ele o classificador
  tenta inferir pelo CNPJ mais frequente nos próprios arquivos);
- Regime tributário atual (Simples/Presumido/Real; anexo, se Simples).

Gere um slug (minúsculo, sem acento, espaços trocados por hífen):

```bash
python3 -c "
import sys, re, unicodedata
s = unicodedata.normalize('NFKD', sys.argv[1])
s = ''.join(c for c in s if not unicodedata.combining(c))
print(re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-'))
" "Nome da Empresa"
```

Se `empresas/<slug>` já existir, avise o usuário e pergunte se é continuação
de uma análise em andamento (neste caso, vá para o passo 3 direto) ou é outra
empresa homônima (use um sufixo, ex. `<slug>-2`). Nunca sobrescreva uma pasta
existente sem confirmação explícita.

Caso contrário, crie a partir do modelo:
```bash
cp -r empresas/_modelo "empresas/<slug>"
```

### 2. Coleta de documentos

Diga claramente ao usuário: *"pode jogar todos os arquivos da empresa em
`empresas/<slug>/novos/` — DRE, balanço, folha, PGDAS-D, XMLs de entrada e
saída — sem se preocupar em organizar por tipo."*

Se o usuário preferir enviar os documentos direto na conversa (colar
conteúdo, anexar arquivo, apontar um caminho fora do projeto), NÃO devolva a
tarefa para ele organizar — salve/copie cada arquivo você mesmo dentro de
`empresas/<slug>/novos/`. O usuário nunca deve precisar mover arquivo
manualmente se já entregou o conteúdo a você.

Pergunte, se ainda não souber:
- Atividade principal / CNAE.
- Se há operação com regime específico da LC 214 (combustível, saúde,
  planos, ZFM, hotelaria, transporte, etc.) — mesmo que superficialmente.

Espere o usuário confirmar que colocou os arquivos (ou que já mandou tudo que
tem — inclusive "não tenho X documento" é uma resposta válida, registre para
o passo 5).

### 3. Confirmação do que chegou

Rode:
```bash
find "empresas/<slug>/novos" -type f
```
Liste para o usuário exatamente o que foi encontrado (nomes de arquivo).
Se a pasta estiver vazia:
- Não avance silenciosamente. Pergunte de novo, ou confirme explicitamente
  que ele quer seguir só com os dados que já digitou na conversa (receita,
  regime, etc.) — nesse caso registre no perfil que não houve documento-fonte
  para nenhum campo, e a análise será por estimativa desde o início.

### 4. Classificação e extração

Delegue ao agente `ingestao-documentos`, passando o caminho `empresas/<slug>`.
Ele roda `motor/classificador_documentos.py` (organiza os arquivos de
`novos/` dentro de `documentos/dre`, `balanco_patrimonial`, `folha`, `pgdas`,
`xmls/entrada`, `xmls/saida`) e monta `empresas/<slug>/perfil_fiscal.json`.

### 5. Checagem de completude (não pule esta etapa)

Depois que o perfil fiscal existir, audite ativamente antes de simular:

- **Documento esperado que não apareceu** (nenhum DRE, nenhum XML de entrada,
  etc.) → explique ao usuário QUAL informação do perfil ficou sem fonte real
  e o que isso muda na análise. Ex.: *"sem XMLs de entrada não há como
  calcular as compras creditáveis reais — vou usar o percentual padrão do
  setor para o crédito de IBS/CBS, que pode super ou subestimar o resultado
  para essa empresa em específico."*
- **Itens em `pendentes_revisao`** (`documentos/_relatorio_classificacao.json`)
  → avise que ficaram sem categoria automática; pergunte o que são ou peça
  para o usuário confirmar se pode ignorá-los.
- **Inconsistência entre documentos** (alíquota efetiva do PGDAS-D não bate
  com a receita segregada, receita do DRE muito diferente da soma dos XMLs,
  folha desproporcional à receita, etc.) → aponte a divergência encontrada e
  pergunte a origem ANTES de seguir. Nunca decida por conta própria qual
  número está certo.
- **Falta algo essencial e não há como estimar com razoabilidade** → PARE,
  não simule com um placeholder arbitrário, e peça o documento que falta.

Toda estimativa ou premissa assumida por falta de dado entra em
`observacoes` do perfil fiscal — nunca fica "silenciosa" apenas na sua
resposta de texto.

### 6. Simulação

Com o perfil aceito (dados reais ou estimativas explicitamente combinadas com
o usuário), siga o fluxo da skill `simulador-reforma`: rode os três cenários
(base/conservador/pessimista) e gere as saídas.

### 7. Entrega final

Apresente ao usuário, nesta ordem:
1. Resumo executivo do resultado (melhor regime por ano, curva da transição).
2. Documentos recebidos × esperados — o que faltou, em lista curta.
3. Toda estimativa/premissa assumida por falta de documento, e o que mudaria
   se o documento aparecer depois.
4. Caminho dos artefatos gerados (`perfil_fiscal.json`, pasta `saidas/`).

## Regras invioláveis

- Nunca invente dado essencial sem avisar. Toda estimativa por falta de
  documento aparece em pelo menos dois lugares: `observacoes` do perfil e a
  entrega final ao usuário.
- Nunca recuse um documento por formato (foto, print, PDF escaneado) — salve
  em `novos/` e deixe o classificador/agente de ingestão decidir; se não
  conseguir extrair automaticamente, leia manualmente com Read.
- LGPD: nunca peça nem registre dados nominais de folha de pagamento — apenas
  o total bruto anual.
- Se a pasta da empresa já existir com um `perfil_fiscal.json`, pergunte antes
  de sobrescrever — pode ser retomada de análise anterior, não recomeço.
