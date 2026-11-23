#!/usr/bin/env bash
set -euo pipefail

PG_ROOT="${AIPOF_PG_ROOT:-/var/lib/ai-proje-ofisi-dbtest/binary/usr}"
PG_BIN="${PG_ROOT}/lib/postgresql/18/bin"
export LD_LIBRARY_PATH="${PG_ROOT}/lib/x86_64-linux-gnu"

PG_SOCKET="${AIPOF_PG_SOCKET:-/var/lib/ai-proje-ofisi-local/socket}"
PG_PORT="${AIPOF_PG_PORT:-55490}"
BACKUP_ROOT="${AIPOF_BACKUP_ROOT:-/var/lib/ai-proje-ofisi-local/backups}"

mkdir -p "${BACKUP_ROOT}"
chmod 700 "${BACKUP_ROOT}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${BACKUP_ROOT}/basebackup-${STAMP}"

"${PG_BIN}/pg_basebackup" \
  -h "${PG_SOCKET}" \
  -p "${PG_PORT}" \
  -D "${TARGET}" \
  -X stream \
  -c fast \
  --manifest-checksums=SHA256

"${PG_BIN}/pg_verifybackup" "${TARGET}"
echo "{\"backup_verified\": true, \"target\": \"${TARGET}\", \"timestamp\": \"${STAMP}\"}"
