#!/bin/bash
# Orquestrador: baixa, descompacta, analisa/filtra, salva o util e descarta o resto.
# Sequencia por parte: download -> unzip -> filtra SP/CNAE -> salva parquet -> apaga .ESTABELE e .zip
# Resumivel (curl -C -) e idempotente (pula partes ja processadas). Pico de disco ~1 parte por vez.
set -uo pipefail

BASE="/Users/helan/Documents/Claudinho/projetos/senac"
DADOS="$BASE/dados_rf"
OUT="$BASE/saida_partes"
PY="$BASE/.venv/bin/python"
URLBASE="https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos/2026-06-14"

mkdir -p "$OUT"
cd "$DADOS" || exit 1
log(){ echo "[$(date '+%H:%M:%S')] $*"; }

for i in $(seq 0 9); do
  zip="Estabelecimentos$i.zip"
  parquet="$OUT/parte_$i.parquet"

  if [ -f "$parquet" ]; then
    log "parte $i: ja processada -> pulando"
    continue
  fi

  exp=$(curl -sIL "$URLBASE/$zip" | grep -i '^content-length' | tail -1 | tr -dc '0-9')
  [ -z "$exp" ] && exp=0
  log "parte $i: baixando $zip (esperado ~$((exp/1024/1024)) MB)"

  ok=0
  for try in $(seq 1 12); do
    curl -sL --retry 5 --retry-delay 5 -C - "$URLBASE/$zip" -o "$zip"
    got=$(stat -f%z "$zip" 2>/dev/null || echo 0)
    if [ "$exp" -gt 0 ] && [ "$got" -ge "$exp" ]; then ok=1; break; fi
    log "parte $i: incompleto ($((got/1024/1024))/$((exp/1024/1024)) MB) -> tentativa $try"
    sleep 5
  done
  if [ "$ok" -ne 1 ]; then
    log "parte $i: FALHA no download -> pulando (rodar de novo retoma)"
    continue
  fi

  member=$(unzip -Z1 "$zip" 2>/dev/null | head -1)
  log "parte $i: descompactando ($member)"
  if ! unzip -o -q "$zip"; then
    log "parte $i: ZIP corrompido -> apagando p/ rebaixar na proxima execucao"
    rm -f "$zip"
    continue
  fi

  # O validador latin-1 do DuckDB recusa alguns arquivos da RFB; converte byte-safe
  # ISO-8859-1 -> UTF-8 (removendo nulls) e o DuckDB le como UTF-8.
  log "parte $i: convertendo ISO-8859-1 -> UTF-8 (byte-safe)"
  tr -d '\000' < "$member" | iconv -f ISO-8859-1 -t UTF-8 > "$member.utf8"

  log "parte $i: analisando/filtrando SP + ativa + CNAEs de residuo"
  if "$PY" "$BASE/extrai.py" parte "$DADOS/$member.utf8" "$parquet"; then
    log "parte $i: OK -> salvou util em $parquet"
  else
    log "parte $i: ERRO no filtro DuckDB -> removendo parquet parcial"
    rm -f "$parquet"
  fi

  rm -f "$zip" "$DADOS/$member" "$DADOS/$member.utf8"
  log "parte $i: descartou bruto (.zip + .ESTABELE + .utf8) -> disco liberado"
done

log "MERGE final: unindo partes uteis + municipios"
cd "$BASE" || exit 1
"$PY" extrai.py merge

log "PIPELINE CONCLUIDO"
