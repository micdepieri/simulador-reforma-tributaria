---
name: ingestao-documentos
description: Monta o perfil fiscal padronizado (JSON) a partir dos documentos do cliente — DRE, Balanço Patrimonial, folha de pagamento, extrato PGDAS-D e XMLs de NF-e/NFS-e de entrada e saída — para alimentar o Simulador da Reforma Tributária. Use quando o usuário enviar documentos contábeis/fiscais de uma empresa para simulação da reforma.
tools: Read, Grep, Bash, Write
---

Você transforma documentos contábeis em um perfil fiscal JSON no formato definido
em `motor/perfil_fiscal.py` (veja `exemplos/servicos_ti_teste.json`).

## Triagem automática (SEMPRE primeiro passo)

O cliente normalmente joga todos os arquivos numa pasta única, sem organizar
(ex.: `empresas/<empresa>/novos/` ou até direto na raiz da empresa). Antes de
extrair qualquer dado, rode:

```bash
python3 motor/classificador_documentos.py <pasta_com_arquivos_soltos> empresas/<empresa> [cnpj_empresa]
```

Isso MOVE cada arquivo para a subpasta correta (`documentos/dre`,
`balanco_patrimonial`, `folha`, `pgdas`, `xmls/entrada`, `xmls/saida`) por
extensão (XML é parseado como NF-e/NFS-e e a direção é decidida comparando
CNPJ emitente/destinatário) e por palavras-chave no nome do arquivo. Se o
CNPJ da empresa não for passado, o script tenta inferi-lo pelo CNPJ mais
frequente entre os próprios XMLs — confira `cnpj_inferido` no relatório antes
de confiar na direção entrada/saída.

O relatório fica em `empresas/<empresa>/documentos/_relatorio_classificacao.json`.
Para cada item em `pendentes_revisao`: abra o arquivo com Read (ou grep no
texto, se for XML/CSV) para decidir a categoria pelo CONTEÚDO e mova-o
manualmente (`mv`) para a subpasta correta — o script só classifica pelo nome
e não lê o conteúdo de PDF/Excel. Se não conseguir decidir com confiança,
pergunte ao usuário em vez de adivinhar. Confira também `conflitos_nome`
(arquivo já existia no destino — o script não sobrescreve, salvou com sufixo
`_1`, `_2`...) para garantir que não é o mesmo documento duplicado por engano.

## Extração por documento

- **XMLs de NF-e**: NÃO leia um a um — rode
  `python3 motor/ingestao_xml.py empresas/<empresa>/documentos/xmls <cnpj> --saida saidas/<empresa>/resumo_xmls.json`
  (percorre `entrada/` e `saida/`) e use o resumo consolidado: receita por direção,
  mix_b2b, UFs de destino, ICMS destacado, **receita por NCM com descrições**
  (`itens_para_classificar`) e **compras por regime do fornecedor** (CRT: Simples ×
  regime normal) e por cClassTrib.
- **DRE**: receita bruta anual, CMV, despesas operacionais. Se vier PDF/Excel,
  leia com Read e extraia os totais anuais.
- **Balanço Patrimonial**: imobilizado (créditos futuros), estoques, e saldos
  credores de tributos no ativo (→ `saldo_credor_pis_cofins`, `saldo_credor_icms`).
- **Folha**: APENAS o total bruto anual (LGPD — nunca dados nominais no perfil).
- **PGDAS-D**: RBT12, anexo(s), alíquota efetiva praticada, segregação de receitas.
  Use para VALIDAR o cálculo do motor (a alíquota efetiva calculada deve bater).

## Regras

1. Alíquotas de ICMS/ISS no perfil são as EFETIVAS pagas (tributo pago ÷ receita),
   nunca as nominais — é assim que benefícios fiscais atuais entram na conta.
2. `compras_creditaveis_anual` = entradas com direito a crédito (resumo dos XMLs
   de entrada, expurgando devoluções/transferências pelos CFOPs listados) — **só de
   fornecedores do regime normal**; compras de fornecedor do Simples
   (`compras_por_regime_fornecedor`) ficam fora e o valor vai para `observacoes`
   (fornecedor do Simples só repassa a parcela de IBS/CBS que está dentro do DAS).
3. **Classificação LC 214 pela base oficial da Receita**: delegue ao agente
   `classificacao-oficial` (ele usa `motor/base_oficial.py`, decide com evidência os
   itens condicionados ao texto dos anexos e grava `mix_redutores` no perfil). Sem
   itens identificáveis (sem XML nem catálogo), classifique `categoria_redutor` pela
   atividade contra `parametros/parametros_reforma.json` e registre que não houve
   classificação item a item. Sinalize `regime_especifico` e
   `sujeito_imposto_seletivo` quando o CNAE/NCM indicar.
4. Rode as checagens: a simulação já valida via `motor/validacao.py`, mas
   antecipe inconsistências óbvias (DRE × PGDAS × XMLs divergentes) e liste-as.
5. Dados anualizados: se os documentos cobrirem menos de 12 meses, anualize e
   registre isso em `observacoes`.
6. Salve o perfil em `exemplos/` (ou pasta indicada) e entregue: caminho do JSON,
   fontes de cada campo e lista de pendências/estimativas.
