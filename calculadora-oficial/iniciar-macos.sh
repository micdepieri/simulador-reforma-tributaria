#!/bin/bash
# Inicia a Calculadora de Tributos oficial (módulo offline) no macOS via Colima.
set -e
colima status >/dev/null 2>&1 || colima start
if ! docker image inspect calculadora-image >/dev/null 2>&1; then
  echo "Importando imagem (primeira vez, ~1 min)..."
  docker import calculadora.tar.gz calculadora-image
fi
docker rm -f calculadora-container >/dev/null 2>&1 || true
docker run -d --rm -p 8080:8080 -p 8081:8081 -w /calculadora \
  --name calculadora-container calculadora-image bash start.sh
echo "Aguardando API (30-60s)..."
until curl -s -o /dev/null -w "%{http_code}" -X POST \
  http://localhost:8080/api/calculadora/regime-geral \
  -H 'Content-Type: application/json' -d '{}' 2>/dev/null | grep -qE "200|400|422|500"; do
  sleep 3
done
echo "Calculadora oficial no ar em http://localhost:8080"
