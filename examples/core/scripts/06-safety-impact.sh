#!/usr/bin/env bash
set -euo pipefail

echo "=== 06: Safety & Impact Analysis ==="

# ── dbwarden check ─────────────────────────────────────────────
# Scans all migration files (both applied and pending) and flags
# potential problems:
#   - DROP COLUMN / DROP TABLE (destructive)
#   - ALTER COLUMN TYPE that might truncate
#   - ALTER COLUMN SET NOT NULL on a table with NULLs
#   - Missing rollback sections
# Run this in CI before merging any schema change PR.
echo "--- Safety check on all migrations ---"
dbwarden check --database primary 2>&1

# ── dbwarden check-impact ──────────────────────────────────────
# Goes further than check: it scans your application source code
# to find references to the columns/tables being changed.
# It uses AST parsing with a grep fallback, so results reflect
# actual code structure, not just text search.
#
# Example output:
#   drop_column on users.username
#     References: 2
#       app/routes/users.py:34  attribute_access
#         .username
#       app/templates/profile.jinja2:12  grep
#         user.username
#
# Run this before any destructive deploy to identify code that
# needs updating before the schema change ships.
echo ""
echo "--- Code impact analysis ---"
# Find the latest migration to check
MIG_FILE=$(ls migrations/primary/*.sql 2>/dev/null | head -1)
if [ -n "$MIG_FILE" ]; then
    MIG_NAME=$(basename "$MIG_FILE")
    MIG_NUM=$(echo "$MIG_NAME" | grep -oP '\d{4}')
    echo "Checking impact of migration $MIG_NUM..."
    dbwarden check-impact "$MIG_NUM" --database primary 2>&1 || echo "(no impacts found or requires applied migration)"
fi
