#!/usr/bin/env bash
# Instala a Calculadora de Tributos da Receita Federal a partir do código aberto no GitHub
# (Release 15+): módulo do regime regular (porta 8080) e do Simples Nacional (porta 8082).
# Requisitos: git, Java 21+ e python3. Uso, da raiz do projeto: ./calculadora-oficial/instalar-github.sh
# Rode de novo sempre que 'python3 motor/base_oficial.py novidades' avisar migração nova.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINO="$RAIZ/calculadora-oficial"
for cmd in git java python3; do
  command -v "$cmd" >/dev/null || { echo "Comando '$cmd' não encontrado no PATH." >&2; exit 1; }
done

clonar() {  # pasta url
  if [ -d "$DESTINO/$1/.git" ]; then
    echo "Atualizando $1..."; git -C "$DESTINO/$1" pull --ff-only
  else
    echo "Clonando $1..."; git clone --depth 1 "$2" "$DESTINO/$1"
  fi
}
clonar regime-regular   https://github.com/ReceitaFederal/calculadora-rtc-regime-regular.git
clonar simples-nacional https://github.com/ReceitaFederal/calculadora-rtc-simples-nacional.git

echo "Montando o banco normativo oficial..."
python3 "$RAIZ/motor/base_oficial.py" montar --fonte "$DESTINO/regime-regular/flyway/sql"

for m in regime-regular simples-nacional; do
  mkdir -p "$DESTINO/$m/calculadora/db"
  cp "$DESTINO/base/calculadora-pro.db" "$DESTINO/$m/calculadora/db/calculadora-pro.db"
  echo "Compilando $m (primeira vez baixa o Maven; alguns minutos)..."
  (cd "$DESTINO/$m" && ./mvnw -q -B clean package -DskipTests)
done

echo
echo "Pronto. Para subir as APIs: ./calculadora-oficial/executar.sh"
echo "Depois confira: python3 motor/validacao_oficial.py --descobrir"
