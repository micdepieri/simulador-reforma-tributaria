#!/usr/bin/env bash
# Sobe (ou para, com --parar) os dois módulos da Calculadora oficial em segundo plano:
#   regime regular -> http://localhost:8080/api · Simples Nacional -> http://localhost:8082/api
set -euo pipefail
DESTINO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDS="$DESTINO/base/pids.txt"
mkdir -p "$DESTINO/base"

if [ "${1:-}" = "--parar" ]; then
  if [ -f "$PIDS" ]; then
    while read -r pid; do kill "$pid" 2>/dev/null || true; done < "$PIDS"
    rm -f "$PIDS"; echo "Calculadora oficial parada."
  else
    echo "Nenhum processo registrado."
  fi
  exit 0
fi

: > "$PIDS"
for par in "regime-regular:api-regime-geral.jar:8080" "simples-nacional:api-simples-nacional.jar:8082"; do
  IFS=: read -r pasta jar porta <<< "$par"
  [ -f "$DESTINO/$pasta/target/$jar" ] || { echo "JAR não encontrado em $pasta — rode instalar-github.sh antes." >&2; exit 1; }
  # o JAR precisa rodar da raiz do módulo para achar ./calculadora/db/calculadora-pro.db
  (cd "$DESTINO/$pasta" && nohup java -Dspring.profiles.active=offline -jar "target/$jar" \
      > "$DESTINO/base/$pasta.log" 2>&1 & echo $! >> "$PIDS")
  echo "$pasta: iniciando na porta $porta"
done
echo "Aguarde ~20s e confira: python3 motor/validacao_oficial.py --descobrir"
echo "Para parar: ./calculadora-oficial/executar.sh --parar"
