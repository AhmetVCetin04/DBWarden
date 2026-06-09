---
seo:
  title: Rolling Back - DBWarden Documentation
  description: Rollback executes the -- rollback section of applied migration files.
  canonical: https://emiliano-gandini-outeda.github.io/DBWarden/tutorial/rolling-back/
  robots: index,follow
  og:
    type: website
    title: Rolling Back - DBWarden Documentation
    description: Rollback executes the -- rollback section of applied migration files.
    url: https://emiliano-gandini-outeda.github.io/DBWarden/tutorial/rolling-back/
    image: https://emiliano-gandini-outeda.github.io/DBWarden/assets/icon.png
    site_name: DBWarden Documentation
  twitter:
    card: summary_large_image
    title: Rolling Back - DBWarden Documentation
    description: Rollback executes the -- rollback section of applied migration files.
    image: https://emiliano-gandini-outeda.github.io/DBWarden/assets/icon.png
  schema_jsonld:
    '@context': https://schema.org
    '@type': WebPage
    name: Rolling Back - DBWarden Documentation
    url: https://emiliano-gandini-outeda.github.io/DBWarden/tutorial/rolling-back/
    description: Rollback executes the -- rollback section of applied migration files.
    image: https://emiliano-gandini-outeda.github.io/DBWarden/assets/icon.png
    publisher:
      '@type': Organization
      name: Emiliano Gandini Outeda
---

# Rolling Back

Rollback executes the `-- rollback` section of applied migration files, reversing
each change in dependency-safe order.

## What you'll learn

- how rollback selection works
- when to use `--count` vs `--to-version`
- how generated rollback SQL is verified
- auto-generated rollback capabilities per operation type

## Prerequisites

- applied migration history exists
- rollback SQL is defined in target migration files

## Run it

```bash
# Rollback the most recent migration
dbwarden rollback --database primary

# Rollback exactly N migrations
dbwarden rollback --database primary --count 2

# Rollback to a specific version (reverts all applied after it)
dbwarden rollback --database primary --to-version 0007
```

The `--count` flag uses `ORDER BY applied_at DESC, version DESC` for deterministic
ordering — even when multiple migrations share the same second-precision timestamp.

## What happened

1. DBWarden loads applied migration history
2. Selects rollback candidates (last N or all after version)
3. Acquires a migration lock (prevents concurrent runs)
4. Executes rollback SQL in reverse dependency order
5. Updates migration metadata records
6. Releases the migration lock

## Auto-generated rollback SQL

DBWarden generates rollback SQL for every auto-generated migration. Each operation
type has a verified upgrade/rollback pair:

### PostgreSQL

| Operation | Upgrade | Rollback | Status |
|-----------|---------|----------|--------|
| `create_table` | `CREATE TABLE ...` | `DROP TABLE ...` | ✅ |
| `drop_table` | `DROP TABLE ...` | `CREATE TABLE ... (see snapshot)` | ✅ (schema in snapshot) |
| `rename_column` | `RENAME COLUMN old TO new` | `RENAME COLUMN new TO old` | ✅ |
| `add_column` | `ADD COLUMN ...` | `DROP COLUMN ...` | ✅ |
| `drop_column` | `DROP COLUMN ...` | `ADD COLUMN ... <type>` | ✅ (type restored) |
| `alter_column_type` | `ALTER COLUMN ... TYPE new` | `ALTER COLUMN ... TYPE old` | ✅ (snap_type used) |
| `alter_column_nullable` | `SET/DROP NOT NULL` | inverse `SET/DROP NOT NULL` | ✅ |
| `alter_column_default` | `SET/DROP DEFAULT` | inverse `SET/DROP DEFAULT` | ✅ |
| `add_foreign_key` | `ADD CONSTRAINT ... FK` | `DROP CONSTRAINT ...` | ✅ |
| `drop_foreign_key` | `DROP CONSTRAINT ...` | `ADD CONSTRAINT ... FK ...` | ✅ (real SQL, not placeholder) |
| `add_index` | `CREATE INDEX ...` | `DROP INDEX ...` | ✅ |
| `drop_index` | `DROP INDEX ...` | `CREATE INDEX ...` | ✅ |
| `add_autoincrement` | `CREATE SEQUENCE + SET DEFAULT` | `DROP DEFAULT + DROP SEQUENCE` | ✅ |
| `remove_autoincrement` | `DROP DEFAULT + DROP SEQUENCE` | `CREATE SEQUENCE + SET DEFAULT` | ✅ |
| `alter_table_comment` | `COMMENT ON TABLE IS ...` | `COMMENT ON TABLE IS 'previous'` | ✅ |
| `alter_column_comment` | `COMMENT ON COLUMN IS ...` | `COMMENT ON COLUMN IS 'previous'` | ✅ |
| `create_index_concurrently` | `CREATE INDEX CONCURRENTLY ...` | `DROP INDEX ...` | ✅ |

### ClickHouse

| Operation | Upgrade | Rollback | Status |
|-----------|---------|----------|--------|
| `add_index` | `ALTER TABLE ADD INDEX ...` | `ALTER TABLE DROP INDEX ...` | ✅ |
| `drop_index` | `ALTER TABLE DROP INDEX ...` | `ALTER TABLE ADD INDEX ... TYPE ...` | ✅ |
| `modify TTL` | `ALTER TABLE MODIFY TTL ...` | `ALTER TABLE MODIFY TTL <previous>` | ✅ |
| `modify ORDER BY` | `ALTER TABLE MODIFY ORDER BY ...` | `ALTER TABLE MODIFY ORDER BY <previous>` | ✅ |
| `modify SETTING` | `ALTER TABLE MODIFY SETTING ...` | `ALTER TABLE MODIFY SETTING <previous>` | ✅ |
| `modify column` | `ALTER TABLE MODIFY COLUMN ...` | `ALTER TABLE MODIFY COLUMN <previous>` | ✅ |
| `rename_table` | `RENAME TABLE ... TO ...` | `RENAME TABLE ... TO ...` | ✅ |

### When rollback is a comment

These operations generate commented-out rollback SQL indicating manual migration is required:

| Operation | Why |
|-----------|-----|
| `alter_enum_add_value` | PostgreSQL cannot remove individual enum values |
| `engine_change` (ClickHouse) | Requires table recreation |
| `partition_change` (PostgreSQL) | Requires table rebuild |
| `safe_type_change` steps 2-4 | Data migration SQL needs manual review |

### make-rollback tool

The `dbwarden make-rollback` command generates a `.rollback.sql` file from an
existing migration file using heuristic SQL reversal:

```bash
dbwarden make-rollback migrations/primary__0005_add_table.sql
# Creates: migrations/primary__0005_add_table.rollback.sql
```

Supported patterns: `CREATE TABLE`, `CREATE MATERIALIZED VIEW`,
`CREATE DICTIONARY`, `ALTER TABLE ADD COLUMN`, `CREATE INDEX`,
`CREATE UNIQUE INDEX` (including `CONCURRENTLY` variant).

## Common failure modes

- rollback SQL doesn't match current schema state
- data rollback assumptions are invalid
- lock conflicts from concurrent migration process

When rollback is risky, prefer a forward-fix migration.

Reference: [Safe Deployment](../advanced/safe-deployment.md)

See also: [Cookbook: Apply & Inspect](../cookbook/03-apply-and-inspect.md)
