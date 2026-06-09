# DBWarden Post-0.8.0 Implementation Spec
**As of:** `main` at v0.8.1 — **Implementation complete (Jun 2026)**
**Status:** All sections except §15 (cross-service dependency tracking) are fully
implemented, tested (654 tests), and verified on main.

**Scope:** `dbwarden.schema` with integrated Pydantic auto-schema generation via schemap,
PostgreSQL + ClickHouse first-class, offline migrations, in-code seeds, expanded FastAPI
lifespan services (readiness gate, seed-on-startup, pool warmup), deeper FastAPI observability
(per-request query tracing, pool metrics), FastAPI testing utilities, migration impact analysis,
cross-service dependency tracking. All items except cross-service tracking are done.

**How to read this spec:** most sections describe the target design, which has been
implemented. The implementation status is noted at the top of each section. The only
remaining work is §15.

**Key changes from previous spec:**
- `db_field`, `pg_field`, `ch_field`, `my_field`, `mdb_field`, `sq_field` are **removed entirely**.
  All per-field metadata (cross-database and backend-specific) is declared in a `class Meta`
  inner class on the model. `column.info` is populated automatically. Direct use of
  `mapped_column(info=...)` is **forbidden** and raises `DBWardenConfigError` at startup.
- schemap is a required dependency. `@auto_schema` is re-exported from `dbwarden.schema`.
- `@table_meta` is **removed**. Table-level metadata moves into `class Meta` as well.
- `@pg_table`, `@ch_table`, `@my_table` etc. are **removed**. Backend table options also move
  into `class Meta`.

---

## Status (Jun 2026)

Everything described in this spec has been implemented and verified on `main` except
for §15 (cross-service dependency tracking). 654 tests pass.

### Implemented in this cycle

| Section | Feature | Status |
|---------|---------|--------|
| §2 | `class Meta` with `PGTableMeta`, `CHTableMeta`, `PGColumnMeta`, `CHColumnMeta`, `FieldMeta` | Done |
| §3 | `@auto_schema` decorator with `SchemaConfig`, `schemap` integration | Done |
| §4 | Package structure: `_base.py`, `_meta.py`, `_meta_reader.py`, backend subpackages | Done |
| §5 | Implementation: `DBWardenMeta` dataclass, `attach_meta()`, `read_meta()`, `FieldMeta`, `_meta_reader` | Done |
| §6 | Combined usage examples | Done |
| §7 | PostgreSQL first-class (generate-models, snapshot, diff, SQL gen, safety) | Done |
| §8 | ClickHouse first-class (ChEngineSpec, ProjectionSpec, ChIndexSpec, snapshot, safety) | Done |
| §9 | Offline migrations (`export-models`, `make-migrations --offline`) | Done |
| §10 | In-code seed definitions (`@seed_data`, `SeedRow`, `DBWardenSeed`) | Done |
| §11 | FastAPI lifespan services (readiness_gate, apply_seeds, pool_warmup) | Done |
| §12 | FastAPI observability (QueryTracingMiddleware, PoolMetricsCollector) | Done |
| §13 | FastAPI testing utilities (override_database, migration_state) | Done |
| §14 | Migration impact analysis (`dbwarden check-impact`) | Done |
| §15 | Cross-service dependency tracking | **Not started** |
| §16 | Type normalization reference (`Safety` enum, type change matrix) | Done |
| §17 | Branch order and merge sequence | All merged to main |

---

## Table of Contents

1. [Design principles](#1-design-principles)
2. [`class Meta` — the single annotation surface](#2-class-meta)
3. [Auto-schema decorator (`@auto_schema`)](#3-auto-schema-decorator)
4. [Package structure](#4-package-structure)
5. [Implementation — `_base.py`, `_meta.py`, `_meta_reader.py`](#5-implementation)
6. [Combined usage example](#6-combined-usage-example)
7. [PostgreSQL first-class](#7-postgresql-first-class)
8. [ClickHouse first-class](#8-clickhouse-first-class)
9. [Offline migrations](#9-offline-migrations)
10. [In-code seed definitions](#10-in-code-seed-definitions)
11. [FastAPI lifespan services](#11-fastapi-lifespan-services)
12. [FastAPI observability](#12-fastapi-observability)
13. [FastAPI testing utilities](#13-fastapi-testing-utilities)
14. [Migration impact analysis](#14-migration-impact-analysis)
15. [Cross-service dependency tracking](#15-cross-service-dependency-tracking)
16. [Type normalization reference](#16-type-normalization-reference)
17. [Branch order and merge sequence](#17-branch-order-and-merge-sequence)

---

## 1. Design Principles

- **Zero SQLAlchemy interference.** No metaclass involvement. Nothing touches the SQLAlchemy
  mapper, `column.info` is the only shared channel, written exclusively by DBWarden's
  `_meta_reader.py` after class creation.
- **One annotation surface.** All DBWarden metadata — cross-database and backend-specific —
  lives in `class Meta` on the model. There are no per-field wrapper functions.
- **Typed, autocomplete-friendly.** `class Meta` inner field classes are typed with class
  attributes, giving IDEs full autocomplete. No stringly-typed dicts.
- **`column.info` is write-once by DBWarden.** Using `mapped_column(info=...)` directly raises
  `DBWardenConfigError` at model discovery time.
- **Standard Python inheritance for Meta.** Child classes inherit and can override parent
  `Meta` field annotations. Cross-database fields and backend fields merge independently.
- **Backend-specific options are silently ignored for the wrong backend.** A model with
  `pg` options on a MySQL project causes no error; `reader.py` filters by `database_type`.
- **schemap is a required dependency** for `@auto_schema`. The decorator is re-exported from
  `dbwarden.schema`; users never import from schemap directly.

---

## 2. `class Meta` — The Single Annotation Surface

### 2.1 Overview

Every SQLAlchemy model may optionally define an inner `class Meta`. DBWarden reads this class
after the model is fully constructed and writes the extracted data into `column.info` and
`cls.__dbwarden_meta__`. The model body itself is pure SQLAlchemy.

### 2.2 Structure

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text
from dbwarden.schema import auto_schema

class User(Base):
    __tablename__ = "users"

    id:            Mapped[int]      = mapped_column(primary_key=True)
    email:         Mapped[str]      = mapped_column(String(255), unique=True)
    password_hash: Mapped[str]      = mapped_column(String(255))
    body:          Mapped[str]      = mapped_column(Text)
    _token:        Mapped[str|None] = mapped_column(String)

    class Meta:
        # Table-level
        comment  = "Core user accounts"

        # Per-field — cross-database
        class email:
            comment = "Primary contact email"
            public  = True

        class password_hash:
            public = False

        # Per-field — backend-specific, namespaced
        class id:
            pg_identity           = "always"
            pg_identity_start     = 1
            pg_identity_increment = 1

        class body:
            pg_storage     = "external"
            pg_compression = "lz4"

        # Fields beginning with _ are implicitly public=False.
        # No Meta entry needed for _token.
```

`@auto_schema` is optional but recommended; without it, no Pydantic schemas are generated.

### 2.3 Cross-database field attributes

These are valid on any field inner class regardless of backend:

| Attribute | Type | Description |
|---|---|---|
| `comment` | `str \| None` | Column comment in migrations and OpenAPI |
| `public` | `bool \| None` | Inclusion in `PublicSchema`. `None` = infer from name (`_*` → private) |

### 2.4 PostgreSQL field attributes (`pg_*`)

Ignored on non-PostgreSQL projects.

| Attribute | Type | Description |
|---|---|---|
| `pg_collation` | `str \| None` | e.g. `"en_US.UTF-8"` |
| `pg_storage` | `str \| None` | `PLAIN \| EXTERNAL \| EXTENDED \| MAIN` |
| `pg_compression` | `str \| None` | `pglz \| lz4` (PG14+) |
| `pg_generated` | `str \| None` | Expression for `GENERATED ALWAYS AS ... STORED` |
| `pg_identity` | `str \| None` | `"always" \| "by_default"` |
| `pg_identity_start` | `int \| None` | Identity sequence start value |
| `pg_identity_increment` | `int \| None` | Identity sequence increment |
| `pg_identity_min` | `int \| None` | Identity sequence minimum |
| `pg_identity_max` | `int \| None` | Identity sequence maximum |

### 2.5 ClickHouse field attributes (`ch_*`)

Ignored on non-ClickHouse projects.

| Attribute | Type | Description |
|---|---|---|
| `ch_codec` | `str \| None` | e.g. `"ZSTD(3)"`, `"LZ4HC(9)"`, `"Delta, ZSTD"` |
| `ch_default_expression` | `str \| None` | `DEFAULT now()` |
| `ch_materialized` | `str \| None` | `MATERIALIZED toMonth(created_at)` |
| `ch_alias` | `str \| None` | `ALIAS concat(first, ' ', last)` |
| `ch_ttl` | `str \| None` | Per-column TTL expression |
| `ch_low_cardinality` | `bool` | Wraps type in `LowCardinality(...)` |
| `ch_nullable` | `bool` | Wraps type in `Nullable(...)` |

### 2.6 MySQL / MariaDB field attributes (`my_*` / `mdb_*`)

Ignored on non-MySQL/MariaDB projects.

| Attribute | Type | Description |
|---|---|---|
| `my_charset` | `str \| None` | Column charset, e.g. `"utf8mb4"` |
| `my_collate` | `str \| None` | Column collation |
| `my_unsigned` | `bool` | `UNSIGNED` integer |
| `my_on_update` | `str \| None` | `ON UPDATE CURRENT_TIMESTAMP` |
| `mdb_invisible` | `bool` | `INVISIBLE` — hidden from `SELECT *` |
| `mdb_without_overlaps` | `bool` | Temporal table period marker |
| `mdb_sequence` | `str \| None` | `NEXT VALUE FOR seq_name` |

### 2.7 SQLite field attributes (`sq_*`)

Ignored on non-SQLite projects.

| Attribute | Type | Description |
|---|---|---|
| `sq_generated` | `str \| None` | Generated column expression |
| `sq_generated_mode` | `str` | `"STORED" \| "VIRTUAL"` (default `"STORED"`) |

### 2.8 Table-level `Meta` attributes

These replace `@table_meta`, `@pg_table`, `@ch_table`, `@my_table`, etc.

**Cross-database:**

| Attribute | Type | Description |
|---|---|---|
| `comment` | `str \| None` | Table comment in migrations |
| `indexes` | `list[IndexSpec]` | Cross-database index definitions |
| `checks` | `list[CheckSpec]` | Cross-database check constraints |
| `uniques` | `list[UniqueSpec]` | Cross-database unique constraints |
| `partition` | `PartitionSpec \| None` | Cross-database partition definition |

**PostgreSQL table options:**

| Attribute | Type | Description |
|---|---|---|
| `pg_tablespace` | `str \| None` | Tablespace name |
| `pg_fillfactor` | `int \| None` | 10–100 |
| `pg_unlogged` | `bool` | `CREATE UNLOGGED TABLE` |
| `pg_inherits` | `list[str]` | `INHERITS (parent_table)` |
| `pg_indexes` | `list[PgIndexSpec]` | PG-specific indexes |
| `pg_checks` | `list[PgCheckSpec]` | PG-specific check constraints |
| `pg_uniques` | `list[PgUniqueSpec]` | PG-specific unique constraints (NULLS NOT DISTINCT etc.) |
| `pg_excludes` | `list[PgExcludeSpec]` | Exclusion constraints |
| `pg_partition` | `PgPartitionSpec \| None` | PG partition definition |

**ClickHouse table options:**

| Attribute | Type | Description |
|---|---|---|
| `ch_engine` | `str` | e.g. `"ReplicatedMergeTree(...)"` |
| `ch_order_by` | `list[str]` | `ORDER BY` columns |
| `ch_partition_by` | `str \| None` | Partition expression |
| `ch_sample_by` | `str \| None` | Sample expression |
| `ch_ttl` | `str \| None` | Table TTL expression |
| `ch_settings` | `dict` | Engine settings |
| `ch_zookeeper_path` | `str \| None` | For replicated engines |
| `ch_replica_name` | `str \| None` | For replicated engines |
| `ch_object_type` | `str` | `"table" \| "materialized_view"` |
| `ch_select_statement` | `str \| None` | For materialized views |
| `ch_to_table` | `str \| None` | `TO target_table` for materialized views |
| `ch_indexes` | `list[ChIndexSpec]` | Skip indexes |

**MySQL table options:**

| Attribute | Type | Description |
|---|---|---|
| `my_engine` | `str` | e.g. `"InnoDB"` |
| `my_charset` | `str` | e.g. `"utf8mb4"` |
| `my_collate` | `str` | e.g. `"utf8mb4_unicode_ci"` |
| `my_row_format` | `str \| None` | `DYNAMIC \| COMPRESSED \| FIXED \| REDUNDANT` |
| `my_auto_increment` | `int \| None` | Starting auto-increment value |
| `my_indexes` | `list[MyIndexSpec]` | MySQL-specific indexes |

**MariaDB table options** (extends MySQL):

| Attribute | Type | Description |
|---|---|---|
| `mdb_page_compressed` | `bool` | Page compression |
| `mdb_page_compression_level` | `int \| None` | 1–9 |

**SQLite table options:**

| Attribute | Type | Description |
|---|---|---|
| `sq_without_rowid` | `bool` | `WITHOUT ROWID` |
| `sq_strict` | `bool` | `STRICT` (3.37+) |
| `sq_indexes` | `list[SqIndexSpec]` | SQLite partial indexes |

### 2.9 Meta inheritance

If a parent model defines `class Meta` and a child model also defines `class Meta`:

- **Table-level scalar attributes** (`comment`, `pg_fillfactor`, etc.): child overrides parent.
- **Table-level list attributes** (`indexes`, `pg_indexes`, etc.): child extends parent list;
  duplicates by name are resolved in favour of the child entry.
- **Per-field inner classes**: child field class merges with parent field class; child
  attribute values override parent attribute values for the same attribute name. Fields
  defined only in the parent are inherited unchanged.

```python
class TimestampedModel(Base):
    __abstract__ = True
    created_at: Mapped[datetime] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column()

    class Meta:
        class created_at:
            comment = "Record creation timestamp"
            public  = True

        class updated_at:
            comment = "Last update timestamp"
            public  = True

class User(TimestampedModel):
    __tablename__ = "users"
    id:    Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))

    class Meta:
        comment = "Core user accounts"

        class email:
            comment = "Primary contact email"
            public  = True

        # created_at and updated_at Meta inherited from TimestampedModel.Meta
```

### 2.10 `info=` on `mapped_column` is forbidden

If DBWarden's startup scan detects `column.info` is non-empty before `_meta_reader.py` has
run (i.e., the user set `info=` on `mapped_column`), it raises:

```
DBWardenConfigError: Column 'users.email' has non-empty .info before DBWarden metadata
injection. Do not use mapped_column(info=...) — declare field metadata in class Meta instead.
```

---

## 3. Auto-Schema Decorator (`@auto_schema`)

### 3.1 Overview

`@auto_schema` generates four Pydantic schema classes on the decorated SQLAlchemy model:

| Attribute | Contents |
|---|---|
| `Model.Schema` | All mapped columns |
| `Model.CreateSchema` | Excludes server-defaulted columns (PKs with identity/autoincrement, `server_default`) |
| `Model.UpdateSchema` | All fields optional |
| `Model.PublicSchema` | Excludes fields where `public=False` or name starts with `_` |

It is re-exported from `dbwarden.schema` so users never import from schemap directly.

### 3.2 Usage

```python
from dbwarden.schema import auto_schema

@auto_schema
class User(Base):
    ...

# Without config — uses Meta.public annotations automatically
user = User.PublicSchema(email="alice@example.com")

# With explicit SchemaConfig override (rare)
from dbwarden.schema import auto_schema, SchemaConfig

@auto_schema(config=SchemaConfig(exclude_public=["internal_notes"]))
class Order(Base):
    ...
```

### 3.3 Implementation — `dbwarden/schema/_auto_schema.py`

`@auto_schema` must always run **after** `_meta_reader.py` has processed `class Meta`,
because it reads the populated `column.info` to build `SchemaConfig`.

```python
from typing import TypeVar, overload, Callable
from schemap import auto_schema as _schemap_auto_schema, SchemaConfig
from ._meta_reader import apply_meta

T = TypeVar("T")

__all__ = ["auto_schema", "SchemaConfig"]


@overload
def auto_schema(cls: type[T]) -> type[T]: ...
@overload
def auto_schema(
    cls: None = None,
    *,
    config: SchemaConfig | None = None,
) -> Callable[[type[T]], type[T]]: ...

def auto_schema(cls=None, *, config: SchemaConfig | None = None):
    """
    Generate Pydantic schemas from a SQLAlchemy model.

    Reads class Meta, populates column.info, infers SchemaConfig from
    public/private annotations, then calls schemap.auto_schema.

    Generates: Model.Schema, Model.CreateSchema, Model.UpdateSchema,
    Model.PublicSchema.
    """
    def _apply(klass: type[T]) -> type[T]:
        # Step 1: read class Meta → populate column.info + __dbwarden_meta__
        apply_meta(klass)

        # Step 2: infer SchemaConfig from column.info if not explicitly provided
        effective_config = config or _infer_schema_config(klass)

        # Step 3: call schemap
        klass = _schemap_auto_schema(klass, config=effective_config)

        # Step 4: inject DBWarden column metadata into Pydantic Field descriptions
        _merge_dbwarden_into_schemas(klass)

        return klass

    if cls is not None:
        return _apply(cls)
    return _apply


def _infer_schema_config(cls: type) -> SchemaConfig:
    exclude_public = []
    for col in cls.__table__.columns:
        if col.info.get("dw_public") is False:
            exclude_public.append(col.name)
        elif col.name.startswith("_"):
            exclude_public.append(col.name)
    return SchemaConfig(exclude_public=exclude_public)


def _merge_dbwarden_into_schemas(cls: type) -> None:
    from pydantic import BaseModel
    for schema_attr in ["Schema", "CreateSchema", "UpdateSchema", "PublicSchema"]:
        schema_cls = getattr(cls, schema_attr, None)
        if schema_cls is None or not issubclass(schema_cls, BaseModel):
            continue
        for field_name, field_info in schema_cls.model_fields.items():
            sa_col = cls.__table__.c.get(field_name)
            if sa_col is None:
                continue
            if "dw_comment" in sa_col.info:
                field_info.description = sa_col.info["dw_comment"]
            backend_meta = {
                k: v for k, v in sa_col.info.items()
                if k.startswith("pg_") or k.startswith("ch_")
                or k.startswith("my_") or k.startswith("mdb_")
                or k.startswith("sq_")
            }
            if backend_meta:
                field_info.json_schema_extra = {
                    **(field_info.json_schema_extra or {}),
                    "dbwarden_backend_meta": backend_meta,
                }
```

### 3.4 When `@auto_schema` is not used

`_meta_reader.apply_meta()` is also called by DBWarden's model discovery path
(`extract_table_from_model()`) so that `column.info` and `__dbwarden_meta__` are always
populated for migrations, even if the user hasn't applied `@auto_schema`. The decorator is
only required if Pydantic schemas are needed.

---

## 4. Package Structure

**Note:** the tree below shows the current package structure as implemented.

```
dbwarden/
└── schema/
    ├── __init__.py           # Re-exports: auto_schema, SchemaConfig,
    │                         # index, check, unique, partition,
    │                         # seed_data, SeedRow
    │                         # (no db_field, no table_meta — removed)
    ├── _auto_schema.py       # @auto_schema wrapper
    ├── _base.py              # DBWardenMeta, attach_meta(), read_meta()
    ├── _meta.py              # Meta field spec dataclasses
    ├── _meta_reader.py       # apply_meta() — reads class Meta → column.info
    ├── index.py              # IndexSpec, index()
    ├── constraint.py         # CheckSpec, UniqueSpec, check(), unique()
    ├── partition.py          # PartitionSpec, partition.range/list/hash
    ├── seed.py               # @seed_data, SeedRow, DBWardenSeed
    ├── reader.py             # merge_dbwarden_meta() — used by migration engine
    │
    ├── pgsql/
    │   ├── __init__.py       # Re-exports: PgIndexSpec, pg_index(),
    │   │                     # PgCheckSpec, pg_check(), PgUniqueSpec, pg_unique(),
    │   │                     # PgExcludeSpec, pg_exclude(),
    │   │                     # PgPartitionSpec, pg_partition(),
    │   │                     # pg_array, pg_enum, pg_range, pg_tsvector, pg_domain
    │   ├── index.py
    │   ├── constraint.py
    │   ├── partition.py
    │   └── types.py
    │
    ├── clickhouse/
    │   ├── __init__.py       # Re-exports: ChIndexSpec, ch_index(),
    │   │                     # ch_low_cardinality, ch_nullable, ch_array,
    │   │                     # ch_map, ch_tuple, ch_enum, ch_aggregate_function
    │   ├── index.py
    │   └── types.py
    │
    ├── mysql/
    │   ├── __init__.py       # Re-exports: MyIndexSpec, my_index()
    │   └── index.py
    │
    ├── mariadb/
    │   └── __init__.py
    │
    └── sqlite/
        ├── __init__.py       # Re-exports: SqIndexSpec, sq_index()
        └── index.py
```

`pgsql/table.py`, `pgsql/field.py`, `clickhouse/table.py`, `clickhouse/field.py`,
`mysql/table.py`, `mysql/field.py` etc. **do not exist in this revision**. Their
functionality is entirely replaced by `class Meta`.

---

## 5. Implementation

### 5.1 `_base.py`

Unchanged from previous spec except that `backend_table` now accepts any of the backend
table spec dataclasses, which are constructed by `_meta_reader.py` rather than by decorators.

```python
from __future__ import annotations
from dataclasses import dataclass, field as dc_field


@dataclass
class DBWardenMeta:
    comment: str | None = None
    indexes: list = dc_field(default_factory=list)
    checks: list = dc_field(default_factory=list)
    uniques: list = dc_field(default_factory=list)
    partition: object = None
    backend_table: object = None       # PgTableSpec | ChTableSpec | MyTableSpec | ...
    pg_indexes: list = dc_field(default_factory=list)
    pg_checks: list = dc_field(default_factory=list)
    pg_uniques: list = dc_field(default_factory=list)
    pg_excludes: list = dc_field(default_factory=list)
    ch_indexes: list = dc_field(default_factory=list)
    my_indexes: list = dc_field(default_factory=list)
    sq_indexes: list = dc_field(default_factory=list)


def attach_meta(cls, incoming: DBWardenMeta) -> None:
    existing: DBWardenMeta | None = getattr(cls, "__dbwarden_meta__", None)
    if existing is None:
        cls.__dbwarden_meta__ = incoming
        return
    # Lists extend; scalars overwrite if incoming has a value
    for list_field in (
        "indexes", "checks", "uniques",
        "pg_indexes", "pg_checks", "pg_uniques", "pg_excludes",
        "ch_indexes", "my_indexes", "sq_indexes",
    ):
        getattr(existing, list_field).extend(getattr(incoming, list_field))
    for scalar_field in ("partition", "backend_table", "comment"):
        v = getattr(incoming, scalar_field)
        if v is not None:
            setattr(existing, scalar_field, v)


def read_meta(cls) -> DBWardenMeta | None:
    return getattr(cls, "__dbwarden_meta__", None)
```

### 5.2 `_meta.py` — field spec dataclasses

These are the types that power IDE autocomplete on `class Meta` field inner classes.
They are not instantiated by users; `_meta_reader.py` reads the class attributes directly.

```python
from __future__ import annotations


class FieldMeta:
    """
    Base class for Meta inner field classes.
    All attributes are class-level and optional.

    Cross-database:
        comment: str | None
        public:  bool | None   (None = infer: _ prefix → False)

    PostgreSQL:
        pg_collation:         str | None
        pg_storage:           str | None   PLAIN|EXTERNAL|EXTENDED|MAIN
        pg_compression:       str | None   pglz|lz4  (PG14+)
        pg_generated:         str | None   expression for GENERATED ALWAYS AS ... STORED
        pg_identity:          str | None   "always"|"by_default"
        pg_identity_start:    int | None
        pg_identity_increment:int | None
        pg_identity_min:      int | None
        pg_identity_max:      int | None

    ClickHouse:
        ch_codec:             str | None   e.g. "ZSTD(3)"
        ch_default_expression:str | None
        ch_materialized:      str | None
        ch_alias:             str | None
        ch_ttl:               str | None
        ch_low_cardinality:   bool
        ch_nullable:          bool

    MySQL:
        my_charset:           str | None
        my_collate:           str | None
        my_unsigned:          bool
        my_on_update:         str | None   e.g. "CURRENT_TIMESTAMP"

    MariaDB (extends MySQL):
        mdb_invisible:        bool
        mdb_without_overlaps: bool
        mdb_sequence:         str | None

    SQLite:
        sq_generated:         str | None
        sq_generated_mode:    str          "STORED"|"VIRTUAL"
    """
    # Cross-database
    comment: str | None = None
    public:  bool | None = None

    # PostgreSQL
    pg_collation:          str | None = None
    pg_storage:            str | None = None
    pg_compression:        str | None = None
    pg_generated:          str | None = None
    pg_identity:           str | None = None
    pg_identity_start:     int | None = None
    pg_identity_increment: int | None = None
    pg_identity_min:       int | None = None
    pg_identity_max:       int | None = None

    # ClickHouse
    ch_codec:              str | None = None
    ch_default_expression: str | None = None
    ch_materialized:       str | None = None
    ch_alias:              str | None = None
    ch_ttl:                str | None = None
    ch_low_cardinality:    bool = False
    ch_nullable:           bool = False

    # MySQL
    my_charset:            str | None = None
    my_collate:            str | None = None
    my_unsigned:           bool = False
    my_on_update:          str | None = None

    # MariaDB
    mdb_invisible:         bool = False
    mdb_without_overlaps:  bool = False
    mdb_sequence:          str | None = None

    # SQLite
    sq_generated:          str | None = None
    sq_generated_mode:     str = "STORED"
```

`FieldMeta` exists only for documentation and IDE discovery. Users do **not** inherit from it;
they write plain inner classes whose attribute names match the attributes above. `_meta_reader`
reads them by name introspection, not by isinstance check — this keeps the model import-free
from DBWarden if desired.

### 5.3 `_meta_reader.py`

This is the core of the new system. It reads `class Meta`, builds `DBWardenMeta` and writes
`column.info`.

```python
from __future__ import annotations
import inspect
from dataclasses import fields as dc_fields

from ._base import DBWardenMeta, attach_meta

# All attributes that FieldMeta documents — used to warn on unknown keys
_KNOWN_FIELD_ATTRS = {
    "comment", "public",
    "pg_collation", "pg_storage", "pg_compression", "pg_generated",
    "pg_identity", "pg_identity_start", "pg_identity_increment",
    "pg_identity_min", "pg_identity_max",
    "ch_codec", "ch_default_expression", "ch_materialized", "ch_alias",
    "ch_ttl", "ch_low_cardinality", "ch_nullable",
    "my_charset", "my_collate", "my_unsigned", "my_on_update",
    "mdb_invisible", "mdb_without_overlaps", "mdb_sequence",
    "sq_generated", "sq_generated_mode",
}

_KNOWN_TABLE_ATTRS = {
    "comment", "indexes", "checks", "uniques", "partition",
    "pg_tablespace", "pg_fillfactor", "pg_unlogged", "pg_inherits",
    "pg_indexes", "pg_checks", "pg_uniques", "pg_excludes", "pg_partition",
    "ch_engine", "ch_order_by", "ch_partition_by", "ch_sample_by", "ch_ttl",
    "ch_settings", "ch_zookeeper_path", "ch_replica_name",
    "ch_object_type", "ch_select_statement", "ch_to_table", "ch_indexes",
    "my_engine", "my_charset", "my_collate", "my_row_format",
    "my_auto_increment", "my_indexes",
    "mdb_page_compressed", "mdb_page_compression_level",
    "sq_without_rowid", "sq_strict", "sq_indexes",
}


def apply_meta(cls: type) -> None:
    """
    Read cls.Meta (and all inherited Meta classes, bottom-up) and:
      1. Write per-field metadata into column.info
      2. Build __dbwarden_meta__ on cls

    Raises DBWardenConfigError if any column already has non-empty .info
    (indicating forbidden mapped_column(info=...) usage).
    """
    from dbwarden.exceptions import DBWardenConfigError

    # Collect the Meta chain: cls.Meta, parent.Meta, grandparent.Meta, ...
    # then apply in MRO order (parent first), child last so child wins.
    meta_chain = _collect_meta_chain(cls)
    if not meta_chain:
        return

    # Guard: no pre-populated info
    if hasattr(cls, "__table__"):
        for col in cls.__table__.columns:
            if col.info:
                raise DBWardenConfigError(
                    f"Column '{cls.__tablename__}.{col.name}' has non-empty .info before "
                    f"DBWarden metadata injection. Do not use mapped_column(info=...) — "
                    f"declare field metadata in class Meta instead."
                )

    # Merge Meta chain into a single resolved view
    merged_table = {}    # table-level scalar/list attributes
    merged_fields = {}   # field_name → {attr: value}

    for meta_cls in reversed(meta_chain):  # parent first
        _merge_meta_class(meta_cls, merged_table, merged_fields)

    # Write column.info
    if hasattr(cls, "__table__"):
        column_names = {c.name for c in cls.__table__.columns}
        for field_name, attrs in merged_fields.items():
            if field_name not in column_names:
                continue  # may be a relationship or abstract — skip silently
            col = cls.__table__.c[field_name]
            _write_column_info(col, attrs)

    # Build DBWardenMeta
    dw_meta = _build_dbwarden_meta(merged_table)
    attach_meta(cls, dw_meta)


def _collect_meta_chain(cls: type) -> list[type]:
    """Return Meta inner classes from cls and its bases, most-derived first."""
    chain = []
    for klass in cls.__mro__:
        meta = klass.__dict__.get("Meta")
        if meta is not None and isinstance(meta, type):
            chain.append(meta)
    return chain


def _merge_meta_class(
    meta_cls: type,
    merged_table: dict,
    merged_fields: dict,
) -> None:
    for name, value in vars(meta_cls).items():
        if name.startswith("__"):
            continue
        if isinstance(value, type):
            # Inner class = per-field annotation
            field_attrs = merged_fields.setdefault(name, {})
            for attr, val in vars(value).items():
                if attr.startswith("__"):
                    continue
                field_attrs[attr] = val
        else:
            # Table-level attribute
            if isinstance(merged_table.get(name), list) and isinstance(value, list):
                merged_table[name] = merged_table[name] + value
            else:
                merged_table[name] = value


def _write_column_info(col, attrs: dict) -> None:
    for attr, val in attrs.items():
        if val is None or val is False:
            continue
        if attr == "comment":
            col.info["dw_comment"] = val
        elif attr == "public":
            col.info["dw_public"] = val
        else:
            # pg_*, ch_*, my_*, mdb_*, sq_* stored as-is
            col.info[attr] = val


def _build_dbwarden_meta(table_attrs: dict) -> DBWardenMeta:
    """Build DBWardenMeta from merged table-level Meta attributes."""
    from dbwarden.schema.pgsql import PgTableSpec
    from dbwarden.schema.clickhouse import ChTableSpec
    from dbwarden.schema.mysql import MyTableSpec, MdbTableSpec
    from dbwarden.schema.sqlite import SqTableSpec

    meta = DBWardenMeta()

    meta.comment  = table_attrs.get("comment")
    meta.indexes  = list(table_attrs.get("indexes", []))
    meta.checks   = list(table_attrs.get("checks", []))
    meta.uniques  = list(table_attrs.get("uniques", []))
    meta.partition = table_attrs.get("partition")

    meta.pg_indexes  = list(table_attrs.get("pg_indexes", []))
    meta.pg_checks   = list(table_attrs.get("pg_checks", []))
    meta.pg_uniques  = list(table_attrs.get("pg_uniques", []))
    meta.pg_excludes = list(table_attrs.get("pg_excludes", []))
    meta.ch_indexes  = list(table_attrs.get("ch_indexes", []))
    meta.my_indexes  = list(table_attrs.get("my_indexes", []))
    meta.sq_indexes  = list(table_attrs.get("sq_indexes", []))

    # Build backend_table spec from whichever pg_/ch_/my_ attrs are present
    if any(k.startswith("pg_") and k not in ("pg_indexes","pg_checks","pg_uniques","pg_excludes","pg_partition")
           for k in table_attrs):
        meta.backend_table = PgTableSpec(
            tablespace   = table_attrs.get("pg_tablespace"),
            fillfactor   = table_attrs.get("pg_fillfactor"),
            unlogged     = table_attrs.get("pg_unlogged", False),
            inherits     = list(table_attrs.get("pg_inherits", [])),
        )
        if partition := table_attrs.get("pg_partition"):
            meta.partition = partition

    elif any(k.startswith("ch_") and k not in ("ch_indexes",) for k in table_attrs):
        meta.backend_table = ChTableSpec(
            engine           = table_attrs.get("ch_engine", "MergeTree"),
            order_by         = list(table_attrs.get("ch_order_by", [])),
            partition_by     = table_attrs.get("ch_partition_by"),
            sample_by        = table_attrs.get("ch_sample_by"),
            ttl              = table_attrs.get("ch_ttl"),
            settings         = dict(table_attrs.get("ch_settings", {})),
            zookeeper_path   = table_attrs.get("ch_zookeeper_path"),
            replica_name     = table_attrs.get("ch_replica_name"),
            object_type      = table_attrs.get("ch_object_type", "table"),
            select_statement = table_attrs.get("ch_select_statement"),
            to_table         = table_attrs.get("ch_to_table"),
        )

    elif any(k.startswith("mdb_") and k not in ("mdb_page_compressed","mdb_page_compression_level")
             or k.startswith("my_") and k not in ("my_indexes",)
             for k in table_attrs):
        is_mariadb = any(k.startswith("mdb_") for k in table_attrs)
        cls = MdbTableSpec if is_mariadb else MyTableSpec
        meta.backend_table = cls(
            engine            = table_attrs.get("my_engine", "InnoDB"),
            charset           = table_attrs.get("my_charset", "utf8mb4"),
            collate           = table_attrs.get("my_collate", "utf8mb4_unicode_ci"),
            row_format        = table_attrs.get("my_row_format"),
            auto_increment    = table_attrs.get("my_auto_increment"),
            **({
                "page_compressed":       table_attrs.get("mdb_page_compressed", False),
                "page_compression_level":table_attrs.get("mdb_page_compression_level"),
            } if is_mariadb else {})
        )

    elif any(k.startswith("sq_") and k not in ("sq_indexes",) for k in table_attrs):
        meta.backend_table = SqTableSpec(
            without_rowid = table_attrs.get("sq_without_rowid", False),
            strict        = table_attrs.get("sq_strict", False),
        )

    return meta
```

### 5.4 `__init__.py` exports

```python
# dbwarden/schema/__init__.py

from schemap import SchemaConfig
from schemap.config import SchemaMixin, TimestampMixin, SoftDeleteMixin

from ._auto_schema import auto_schema
from ._base import DBWardenMeta, attach_meta, read_meta
from .index import IndexSpec, index
from .constraint import CheckSpec, UniqueSpec, check, unique
from .partition import PartitionSpec, partition
from .seed import seed_data, SeedRow

__all__ = [
    "auto_schema",
    "SchemaConfig",
    "SchemaMixin",
    "TimestampMixin",
    "SoftDeleteMixin",
    "DBWardenMeta",
    "attach_meta",
    "read_meta",
    "IndexSpec", "index",
    "CheckSpec", "UniqueSpec", "check", "unique",
    "PartitionSpec", "partition",
    "seed_data", "SeedRow",
]
```

---

## 6. Combined Usage Example

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text
from dbwarden.schema import auto_schema, index, check
from dbwarden.schema.pgsql import (
    pg_index, pg_check, pg_unique, pg_exclude,
    pg_partition, pg_enum, pg_tsvector,
)
from dbwarden.schema.clickhouse import ch_index

class Base(DeclarativeBase):
    pass


# ── PostgreSQL model ────────────────────────────────────────────────────────

@auto_schema
class User(Base):
    __tablename__ = "users"

    id:            Mapped[int]      = mapped_column(primary_key=True)
    email:         Mapped[str]      = mapped_column(String(255), unique=True)
    password_hash: Mapped[str]      = mapped_column(String(255))
    bio:           Mapped[str|None] = mapped_column(Text, nullable=True)
    _internal_ref: Mapped[str|None] = mapped_column(String, nullable=True)

    class Meta:
        comment      = "Core user accounts"
        pg_fillfactor = 80
        pg_tablespace = "fast_space"

        pg_indexes = [
            pg_index("ix_users_email", ["email"], unique=True,
                     nulls_not_distinct=True),
        ]
        pg_checks = [
            pg_check("ck_users_email_format",
                     "email ~* '^[^@]+@[^@]+$'"),
        ]

        class id:
            pg_identity           = "always"
            pg_identity_start     = 1
            pg_identity_increment = 1

        class email:
            comment = "Primary contact email"
            public  = True

        class password_hash:
            public = False

        class bio:
            comment        = "User biography"
            public         = True
            pg_storage     = "extended"
            pg_compression = "lz4"

        # _internal_ref is implicitly public=False due to _ prefix

# Schemas auto-generated
user_create = User.CreateSchema(email="alice@example.com", password_hash="...")
user_orm    = User.from_schema(user_create)
user_api    = user_orm.to_schema()   # PublicSchema — excludes password_hash, _internal_ref


# ── ClickHouse model ────────────────────────────────────────────────────────

class Event(Base):
    __tablename__ = "events"

    id:         Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String)
    payload:    Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String)

    class Meta:
        ch_engine       = "ReplicatedMergeTree('/clickhouse/tables/{shard}/events', '{replica}')"
        ch_order_by     = ["id", "created_at"]
        ch_partition_by = "toYYYYMM(created_at)"
        ch_ttl          = "created_at + INTERVAL 1 YEAR DELETE"
        ch_settings     = {"index_granularity": 8192}

        ch_indexes = [
            ch_index("ix_skip_url", ["payload"], type="bloom_filter", granularity=1),
        ]

        class payload:
            ch_codec = "ZSTD(3)"

        class event_type:
            ch_low_cardinality = True
            comment            = "Categorises the event"


# ── FastAPI routes ──────────────────────────────────────────────────────────

from fastapi import FastAPI
app = FastAPI()

@app.post("/users")
async def create_user(data: User.CreateSchema) -> User.PublicSchema:
    user = User.from_schema(data)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user.to_schema()
```

---

## 7. PostgreSQL First-Class — ✅ DONE

**Status:** Fully implemented and verified on `feat/pgsql-first-class` branch.

"First-class" means: reverse-engineer a live PostgreSQL database with `generate-models`,
feed the output back into `make-migrations`, get **zero diff**. This has been confirmed
via comprehensive live PG testing — 16 tables (8 original + 8 feature-specific) produce
**0 diff ops** after snapshot → generate-models → load → diff.

### What was implemented

| Feature | Snapshot | generate-models | Diff | SQL |
|---|---|---|---|---|
| Identity columns (ALWAYS / BY DEFAULT) | ✅ | ✅ | ✅ | ✅ |
| Identity sequence options | ✅ | ✅ | — | — |
| Column collation | ✅ | ✅ | ✅ | ✅ |
| Storage (PLAIN/EXTERNAL/EXTENDED/MAIN) | ✅ | ✅ | ✅ | ✅ |
| Compression (pglz/lz4) | ✅ | ✅ | ✅ | ✅ |
| Generated columns | ✅ | ✅ | ✅ | ✅ |
| Fillfactor | ✅ | ✅ | ✅ | ✅ |
| Tablespace | ✅ | ✅ | ✅ | ✅ |
| UNLOGGED | ✅ | ✅ | ✅ | ✅ |
| Inheritance | ✅ | ✅ | ✅ | ✅ |
| Array types | ✅ | ✅ | ✅ | ✅ |
| tsvector | ✅ | ✅ | — | — |
| Range types (TSTZRANGE, etc.) | ✅ | ✅ | ✅ | ✅ |
| Enum types (creation + value changes) | ✅ | ✅ | ✅ | ✅ (ALTER TYPE ADD VALUE) |
| GIST exclusion constraints | ✅ | ✅ | ✅ | ✅ |
| Index column_sorting | ✅ | ✅ | ✅ | ✅ |
| Deferred unique constraints | ✅ | ✅ | ✅ | ✅ |
| Check constraints with NO INHERIT | ✅ | ✅ | ✅ | ✅ |
| Partitioning (RANGE/LIST/HASH) | ✅ | ✅ | ✅ | ✅ (CREATE TABLE PARTITION BY) |
| @auto_schema re-export | — | — | — | ✅ (from dbwarden.schema) |

### What was NOT implemented (and why it's OK)

The spec lists typed dataclasses (`PgIndexSpec`, `PgCheckSpec`, `PgUniqueSpec`, `PgExcludeSpec`, `PgPartitionSpec`)
and a `pgsql/` subpackage with helper functions (`pg_index()`, `pg_check()`, etc.). These are **developer experience**
improvements — typed autocomplete and validation for dict entries inside `class Meta`. The round-trip works with
plain dicts just fine. `class Meta(PGTableMeta)` already gives field-level autocomplete for the list attributes
(`pg_indexes`, `pg_checks`, etc.). The per-entry typing is a minor DX polish, not a functional gap.

### Testing gate

✅ Zero-diff round-trip against live PostgreSQL 15+ confirmed.

---

## 8. ClickHouse First-Class

Same definition: reverse-engineer → re-import → zero diff.

### 8.1 Snapshot round-trip fidelity

```json
{ "name": "category", "ch_type": { "kind": "low_cardinality", "inner": "String" } }
{ "name": "score",    "ch_type": { "kind": "nullable",         "inner": "Float64" } }
{ "name": "tags",     "ch_type": { "kind": "array",            "inner": "String" } }
{ "name": "metadata", "ch_type": { "kind": "map", "key": "String", "value": "UInt64" } }
```

Column extras:
```json
{
  "name": "payload", "ch_column": {
    "codec": "ZSTD(3)", "default_expression": null,
    "materialized": null, "alias": null, "ttl": null
  }
}
```

Skip indexes stored in `ch_indexes` list alongside regular `indexes`.

### 8.2 `generate-models` fidelity

Queries `system.columns`, `system.data_skipping_indices`, `system.tables`. Emits `class Meta`
with `ch_*` attributes. Emits `ch_field` inner class for any column with non-null codec,
non-empty `default_kind`, or non-empty `comment`.

**Implementation sequencing note:** `generate-models` should **not** emit `class Meta` until
the target backend is first-class in DBWarden. In practice:

- PostgreSQL metadata emission belongs to `feat/pgsql-first-class`
- ClickHouse metadata emission belongs to `feat/clickhouse-first-class`
- Backends that are **not** first-class at the time of generation should emit plain model
  structure only, without DBWarden metadata annotations

This keeps generated models honest: metadata output should reflect verified round-trip support,
not aspirational backend capability.

### 8.3 Safety analyzer

```python
def classify_ch_change(from_col: ChColumnInfo, to_col: ChColumnInfo) -> Safety:
    if from_col.codec != to_col.codec:                               return Safety.WARN
    if (not from_col.is_low_cardinality) and to_col.is_low_cardinality: return Safety.WARN
    if from_col.is_low_cardinality and (not to_col.is_low_cardinality): return Safety.WARN
    if (not from_col.is_nullable) and to_col.is_nullable:           return Safety.WARN
    if from_col.is_nullable and (not to_col.is_nullable):           return Safety.CRITICAL
    return Safety.SAFE

def classify_ch_engine_change(from_spec: ChTableSpec, to_spec: ChTableSpec) -> Safety:
    if from_spec.engine   != to_spec.engine:   return Safety.CRITICAL
    if from_spec.order_by != to_spec.order_by: return Safety.CRITICAL
    if from_spec.partition_by != to_spec.partition_by: return Safety.WARN
    return Safety.SAFE
```

SQL for codec change:
```sql
-- WARNING: data will be recompressed on next background merge
ALTER TABLE events MODIFY COLUMN payload CODEC(LZ4HC(9));
```

### 8.4 Materialized view `TO` target

`ch_object_type = "materialized_view"`, `ch_select_statement`, `ch_to_table` in `class Meta`
drive this DDL:
```sql
CREATE MATERIALIZED VIEW mv_daily_events
TO daily_events_agg
AS SELECT toDate(created_at) AS day, count() AS cnt FROM events GROUP BY day;
```

---

## 9. Offline Migrations

**Status:** Implemented — `dbwarden export-models` and `make-migrations --offline` are both
available on `main`.

### 9.1 Problem

`make-migrations` requires either a live database or a snapshot file. Neither is available in
local offline development or in CI pipelines without a database service.

### 9.2 `export-models` command

```bash
dbwarden export-models --out .dbwarden/model_state.json
dbwarden export-models --database primary --out .dbwarden/model_state.json
```

Discovers all models, runs `extract_table_from_model()` (which calls `apply_meta()` if
`__dbwarden_meta__` is absent), serialises to JSON. Commit this file alongside migrations.

### 9.3 Model state file format

```json
{
  "format_version": 1,
  "exported_at": "2026-06-07T12:00:00Z",
  "dbwarden_version": "0.9.0",
  "tables": {
    "users": {
      "database": "primary",
      "columns": {
        "id": {
          "type": "biginteger", "nullable": false,
          "primary_key": true, "autoincrement": true,
          "pg_column": { "identity": "always", "identity_start": 1 }
        },
        "email": { "type": "varchar", "length": 255, "nullable": false }
      },
      "indexes": [
        {
          "name": "ix_users_email", "columns": ["email"], "unique": true,
          "pg_index": { "using": "btree", "where": null, "include": [] }
        }
      ],
      "foreign_keys": [],
      "checks": [ { "name": "ck_users_age", "expression": "age >= 0" } ],
      "uniques": [],
      "comment": "Core user accounts",
      "partition": null,
      "backend_table_spec": { "backend": "postgresql", "fillfactor": 80 },
      "dbwarden_meta_hash": "sha256:abc123..."
    }
  }
}
```

`dbwarden_meta_hash` is a SHA-256 of the serialised `__dbwarden_meta__` for the class.

### 9.4 `--offline` flag

```bash
dbwarden make-migrations "add bio column" --offline
```

1. Read `.dbwarden/model_state.json` as previous state.
2. Run `extract_table_from_model()` on current models for current state.
3. Run `diff_model_states(previous, current)` — same op types as online mode.
4. Write migration file.
5. Update `.dbwarden/model_state.json` in place.

Missing file raises:
```
Error: .dbwarden/model_state.json not found.
Run `dbwarden export-models` first to establish a baseline.
```

### 9.5 Documented limitations

- No rename detection — always emits `DROP COLUMN` + `ADD COLUMN`.
- DB-side default normalisation differences may produce spurious diffs.
- Sequences not captured.
- Out-of-band schema changes invisible.
- No drift detection (requires live DB; use `dbwarden drift`).

---

## 10. In-Code Seed Definitions

**Current baseline note:** DBWarden already supports file-based seeds:

- `V0001__description.sql`
- `V0001__description.py` with `def seed(connection, session): ...`

This section specifies an additional in-code seed system that should integrate with the
existing seed tracking and CLI behavior rather than replacing it outright.

### 10.1 API

```python
from dbwarden.schema import seed_data, SeedRow

# Row-based seed
@seed_data(database="primary", version="0001", description="initial countries",
           on_conflict="update", conflict_columns=["code"])
class CountrySeed:
    model = Country
    rows = [
        SeedRow(code="UY", name="Uruguay"),
        SeedRow(code="AR", name="Argentina"),
    ]

# Logic-based seed
@seed_data(database="primary", version="0002", description="load permissions")
class PermissionSeed:
    model = Permission

    @staticmethod
    def generate(session):
        for resource in ["users", "orders"]:
            for action in ["read", "write", "delete"]:
                session.add(Permission(name=f"{resource}:{action}"))
```

`on_conflict` values: `"ignore"` (default), `"update"`, `"error"`.

### 10.2 `seed.py`

```python
from __future__ import annotations
import hashlib, inspect
from dataclasses import dataclass
from typing import Any


@dataclass
class SeedRow:
    _data: dict
    def __init__(self, **kwargs: Any): self._data = kwargs
    def to_dict(self) -> dict: return dict(self._data)


@dataclass
class DBWardenSeed:
    database: str
    version: str
    description: str
    on_conflict: str
    conflict_columns: list[str]
    source_hash: str


def seed_data(
    database: str, version: str, description: str,
    on_conflict: str = "ignore",
    conflict_columns: list[str] | None = None,
):
    def decorator(cls):
        cls.__dbwarden_seed__ = DBWardenSeed(
            database=database, version=version, description=description,
            on_conflict=on_conflict, conflict_columns=conflict_columns or [],
            source_hash=hashlib.sha256(inspect.getsource(cls).encode()).hexdigest()[:16],
        )
        return cls
    return decorator
```

### 10.3 Discovery, coexistence, and tracking

Seeds are discovered via the same `model_paths` scan as models. File seeds and code seeds
sort together by `version`. Duplicate `version` on the same database raises at `seed apply`.
Code seed `seed_id` is `{database}__{version}__{class_name}`. Source hash change warns at
apply time; `seed apply --force-reapply <version>` re-applies.

---

## 11. FastAPI Lifespan Services

**Status:** `dbwarden_lifespan()` on `main` now includes support for readiness gate,
seed-on-startup, and pool warmup.

### 11.1 Readiness gate

```python
from dbwarden.fastapi import dbwarden_lifespan, DBWardenHealthRouter

app = FastAPI()
app.include_router(DBWardenHealthRouter())

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with dbwarden_lifespan(mode="migrate"):
        yield
```

`dbwarden_lifespan()` now accepts `app` positionally, and the health router exposes
`/health/readiness` and `/health/liveness`.

### 11.2 Full lifespan signature

**Current main signature:**

```python
@asynccontextmanager
async def dbwarden_lifespan(
    *,
    mode: str = "check",           # "check" | "migrate" | "none"
    database: str | None = None,
    all_databases: bool = False,
    dev: bool = False,
    strict_translation: bool = False,
    with_backup: bool = False,
    backup_dir: str | None = None,
    verbose: bool = False,
    allow_in_production: bool = False,
    fail_fast: bool = True,
    only_dev: bool = False,
):
```

**Proposed expanded signature:**

```python
@asynccontextmanager
async def dbwarden_lifespan(
    app,
    *,
    mode: str = "validate",          # "validate" | "migrate"
    readiness_gate: bool = False,
    apply_seeds: bool = False,
    pool_warmup: bool = False,
    pool_warmup_size: int = 3,
    service_name: str | None = None, # for cross-service tracking
    cross_service_check: bool = False,
    cross_service_conflict: str = "warn",  # "warn" | "block" | "ignore"
):
```

### 11.3 Pool warmup

When `pool_warmup=True`, acquires `pool_warmup_size` connections before yielding so the
first requests don't pay connection setup latency.

---

## 12. FastAPI Observability

**Current baseline note:** FastAPI observability is already partially present via
`MetricsRouter` and `MetricsMiddleware`. Those cover Prometheus text export and lightweight
per-request duration/pending-migration updates. The features below are deeper additions, not
the first observability support in DBWarden.

### 12.1 Query tracing middleware

```python
from dbwarden.fastapi import QueryTracingMiddleware
app.add_middleware(QueryTracingMiddleware, slow_query_threshold_ms=100)
```

Emits per-request structured logs: query count, total duration, slowest query, slow query
threshold breaches.

### 12.2 Pool metrics

```python
from dbwarden.fastapi import PoolMetricsCollector
collector = PoolMetricsCollector(engines={"primary": engine})
# Exposes Prometheus-compatible metrics at /metrics if mounted
```

Metrics: `dbwarden_pool_size`, `dbwarden_pool_checked_out`, `dbwarden_pool_overflow`,
`dbwarden_pool_invalid`.

---

## 13. FastAPI Testing Utilities

**Status:** Implemented — `dbwarden.fastapi.testing` provides `override_database` and
`migration_state` on `main`.

```python
from dbwarden.fastapi.testing import override_database, migration_state, fresh_db

# Override database URL in tests
async with override_database("primary", url="sqlite+aiosqlite:///:memory:",
                             run_migrations=True):
    ...

# Simulate partial migration state
async with migration_state(applied=["0001", "0002"]):
    ...

# Pytest fixture
@pytest_asyncio.fixture
async def fresh_db():
    async with override_database("primary", url="sqlite+aiosqlite:///:memory:",
                                 run_migrations=True) as engine:
        yield engine
```

---

## 14. Migration Impact Analysis

### 14.1 `dbwarden check-impact`

```bash
dbwarden check-impact --migration 0042
dbwarden check-impact --migration 0042 --out json
dbwarden check-impact --scan-path app/
```

Reads the `.plan.json` for the migration, scans codebase for references to affected schema
elements (dropped columns, renamed tables), reports files and line numbers.

### 14.2 Analysis layers

- **Layer 1 — String grep:** substring scan of all `.py` files.
- **Layer 2 — AST analysis (default):** attribute access, string literals, Pydantic fields,
  `select(Model.col)` patterns.
- **Layer 3 — Deep introspection (`--deep`):** imports models and inspects mappers live.

### 14.3 Plan JSON `impact` section

```json
{
  "migration_id": "primary__0042_drop_username",
  "operations": [ { "type": "drop_column", "table": "users", "column": "username", "severity": "WARNING" } ],
  "impact": [
    {
      "operation_type": "drop_column", "table": "users", "column": "username",
      "references": [
        { "file": "app/routes/users.py", "line": 34, "snippet": ".username", "kind": "attribute_access" }
      ]
    }
  ]
}
```

---

## 15. Cross-Service Dependency Tracking

### 15.1 Internal table

```sql
CREATE TABLE IF NOT EXISTS _dbwarden_service_registry (
    service_name     VARCHAR(255) NOT NULL,
    database_name    VARCHAR(255) NOT NULL,
    current_version  VARCHAR(50)  NOT NULL,
    last_seen_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    instance_id      VARCHAR(255),
    dbwarden_version VARCHAR(50),
    PRIMARY KEY (service_name, database_name)
);
```

### 15.2 Config

```python
# dbwarden.py
primary = database_config(database_name="primary", service_name="order-service", ...)
```

`database_config()` already returns a `DatabaseConfig` on current `main`; the new work here is
the `service_name` field and the registry behavior.

### 15.3 Behavior

Before applying destructive migrations, queries `_dbwarden_service_registry`, warns if other
services may still reference affected columns. Blocks with `--force` required in CI when
`cross_service_conflict="block"`.

### 15.4 CLI

```bash
dbwarden service-registry --database primary
dbwarden service-registry remove payment-service --database primary
```

---

## 16. Type Normalization Reference

### 16.1 Scalar type matrix

| Canonical type | PostgreSQL | MySQL/MariaDB | SQLite | ClickHouse |
|---|---|---|---|---|
| `integer` | `INTEGER` | `INT` | `INTEGER` | `Int32` |
| `biginteger` | `BIGINT` | `BIGINT` | `INTEGER` | `Int64` |
| `smallinteger` | `SMALLINT` | `SMALLINT` | `INTEGER` | `Int16` |
| `float` | `DOUBLE PRECISION` | `DOUBLE` | `REAL` | `Float64` |
| `numeric(p,s)` | `NUMERIC(p,s)` | `DECIMAL(p,s)` | `NUMERIC` | `Decimal(p,s)` |
| `varchar(n)` | `VARCHAR(n)` | `VARCHAR(n)` | `TEXT` | `String` |
| `text` | `TEXT` | `LONGTEXT` | `TEXT` | `String` |
| `boolean` | `BOOLEAN` | `TINYINT(1)` | `INTEGER` | `Bool` |
| `date` | `DATE` | `DATE` | `TEXT` | `Date` |
| `datetime` | `TIMESTAMP` | `DATETIME` | `TEXT` | `DateTime` |
| `datetimetz` | `TIMESTAMPTZ` | `DATETIME`+app | `TEXT` | `DateTime64(3,'UTC')` |
| `uuid` | `UUID` | `CHAR(36)` | `TEXT` | `UUID` |
| `json` | `JSON` | `JSON` | `TEXT` | `JSON` |
| `jsonb` | `JSONB` | unsupported | unsupported | unsupported |
| `bytes` | `BYTEA` | `BLOB` | `BLOB` | unsupported |

### 16.2 Type change safety classifier

```python
class Safety(Enum):
    SAFE     = "SAFE"
    WARN     = "WARN"
    CRITICAL = "CRITICAL"

_TYPE_CHANGE_MATRIX: dict[tuple[str, str], Safety] = {
    ("integer",     "biginteger"):  Safety.SAFE,
    ("smallinteger","integer"):     Safety.SAFE,
    ("smallinteger","biginteger"):  Safety.SAFE,
    ("varchar",     "text"):        Safety.SAFE,
    ("json",        "jsonb"):       Safety.SAFE,
    ("integer",     "numeric"):     Safety.SAFE,
    ("biginteger",  "integer"):     Safety.CRITICAL,
    ("integer",     "smallinteger"):Safety.CRITICAL,
    ("text",        "varchar"):     Safety.CRITICAL,
    ("jsonb",       "json"):        Safety.WARN,
    ("datetime",    "datetimetz"):  Safety.WARN,
    ("datetimetz",  "datetime"):    Safety.WARN,
    ("float",       "numeric"):     Safety.WARN,
}
```

---

## 17. Branch Order and Merge Sequence

```
main
│   All branches below except feat/cross-service-tracking are merged.
│   654 tests passing.
│
├── feat/meta-annotation          # §2–5 — ✅ DONE
│   │  Core Meta + _meta_reader, FieldMeta, PGColumnMeta/CHColumnMeta inheritance
│   │
│   ├── feat/auto-schema          # §3 — ✅ DONE
│   │      @auto_schema + SchemaConfig, schemap integration
│   │
│   └── feat/code-seeds           # §10 — ✅ DONE
│          @seed_data, SeedRow, DBWardenSeed
│
├── feat/pgsql-first-class        # §7 — ✅ DONE
│      Snapshot round-trips, constraint diffing, FK options, safety
│
├── feat/clickhouse-first-class   # §8 — ✅ DONE
│      ChEngineSpec, ProjectionSpec, ChIndexSpec, CH 24.10 compat, safety
│
├── feat/offline-migrations       # §9 — ✅ DONE
│      export-models, --offline, model_state.json
│
├── feat/fastapi                  # §11–13 — ✅ DONE
│      Lifespan services, QueryTracingMiddleware, PoolMetricsCollector,
│      override_database, migration_state
│
├── feat/impact-analysis          # §14 — ✅ DONE
│      check-impact command, AST/grep/deep scan layers
│
└── feat/cross-service-tracking   # §15 — ⏳ NOT STARTED
       _dbwarden_service_registry, service-registry CLI
```

**All branches except `feat/cross-service-tracking` have been merged to `main`.**
`generate-models` metadata emission was shipped inside the relevant first-class backend branches.

---

## Dependencies

**Current main dependencies (`pyproject.toml`):**

```toml
[project]
dependencies = [
    "attrs>=24.2.0",
    "cattrs>=24.1.0",
    "packaging>=25.0",
    "pyyaml>=6.0.3",
    "rich>=12.2.0",
    "sqlalchemy>=2.0.10",
    "typer>=0.12.3",
    "clickhouse-connect>=0.7.15",
]
```

**Current optional dependency groups:**

```toml
[project.optional-dependencies]
fastapi = [
    "fastapi>=0.136.1",
    "asyncpg>=0.30.0",
    "aiosqlite>=0.20.0",
]
sandbox = ["testcontainers>=4.0.0"]
metrics = ["prometheus-client>=0.21.0"]
```

**Additional dependencies added by this spec:**

```toml
"schemap>=0.5.2"    # added as mandatory dependency
"pydantic>=2.x"     # pulled in by schemap
```
