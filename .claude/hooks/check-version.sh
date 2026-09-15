#!/usr/bin/env bash
# SessionStart hook: verifica se o repositório local está atualizado com o
# GitHub (origin/main e a última GitHub Release/tag), independente da máquina.
# Nunca deve travar a sessão: qualquer falha (sem rede, sem remoto, etc.)
# apenas emite um aviso e sai com sucesso.

set -u

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR" || exit 0

emit() {
  local msg="$1"
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' \
    "$(printf '%s' "$msg" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ')"
}

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  exit 0
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  exit 0
fi

# macOS nao tem `timeout` por padrao; implementa um timeout portatil via
# processo em background + watchdog.
run_with_timeout() {
  local secs="$1"; shift
  "$@" >/dev/null 2>&1 &
  local pid=$!
  ( sleep "$secs" && kill -TERM "$pid" >/dev/null 2>&1 ) &
  local watchdog=$!
  wait "$pid" 2>/dev/null
  local status=$?
  kill -TERM "$watchdog" >/dev/null 2>&1
  wait "$watchdog" 2>/dev/null
  return $status
}

if ! run_with_timeout 8 git fetch --tags --quiet origin; then
  emit "Aviso de versao: nao foi possivel checar o GitHub (sem rede ou fetch falhou). Nao ha garantia de que este repositorio esteja atualizado com a ultima release."
  exit 0
fi

LOCAL_HEAD="$(git rev-parse HEAD 2>/dev/null)"
REMOTE_MAIN="$(git rev-parse origin/main 2>/dev/null)"
LATEST_TAG="$(git tag -l 'v*' --sort=-v:refname | head -n1)"

STATUS_LINES=()

if [ -n "$REMOTE_MAIN" ] && [ "$LOCAL_HEAD" != "$REMOTE_MAIN" ]; then
  AHEAD_BEHIND="$(git rev-list --left-right --count "HEAD...origin/main" 2>/dev/null)"
  STATUS_LINES+=("HEAD local ($LOCAL_HEAD) difere de origin/main ($REMOTE_MAIN); ahead/behind=$AHEAD_BEHIND.")
fi

if [ -n "$LATEST_TAG" ]; then
  TAG_COMMIT="$(git rev-list -n1 "$LATEST_TAG" 2>/dev/null)"
  if ! git merge-base --is-ancestor "$TAG_COMMIT" HEAD 2>/dev/null; then
    STATUS_LINES+=("A release mais recente no GitHub e $LATEST_TAG, que ainda nao esta incluida no HEAD local.")
  fi
fi

if [ "${#STATUS_LINES[@]}" -gt 0 ]; then
  MSG="ATENCAO - possivel desatualizacao em relacao ao GitHub: "
  for line in "${STATUS_LINES[@]}"; do
    MSG="$MSG $line"
  done
  MSG="$MSG Rode 'git pull origin main --tags' para atualizar antes de confiar nos resultados do simulador."
  emit "$MSG"
else
  emit "Versao OK: repositorio local sincronizado com origin/main e com a ultima release ($LATEST_TAG)."
fi

exit 0
