# API Reference

Complete API documentation for DBWarden's FastAPI integration.

## `get_session`

Returns a FastAPI dependency that yields an `AsyncSession`.

### Signature

```python
def get_session(
    database: str | None = None,
    *,
    dev: bool = False,
) -> Callable[[], AsyncGenerator[AsyncSession, None]]
```

### Parameters

**`database`** : `str | None`, optional
- Database name from DBWarden config
- If `None`, uses the default database
- Default: `None`

**`dev`** : `bool`, keyword-only, optional
- If `True`, uses `dev_database_url` instead of `database_url`
- Useful for local development
- Default: `False`

### Returns

**`Callable[[], AsyncGenerator[AsyncSession, None]]`**
- A dependency function that FastAPI's `Depends()` can consume
- The dependency yields an `AsyncSession` for each request
- Sessions are automatically closed after the request

### Examples

```python
# Default database
SessionDep = Annotated[AsyncSession, Depends(get_session())]

# Specific database
AnalyticsSessionDep = Annotated[AsyncSession, Depends(get_session("analytics"))]

# Dev mode
DevSessionDep = Annotated[AsyncSession, Depends(get_session(dev=True))]
```

### Raises

- **`ValueError`**: If database type is not supported
- **`DBWardenConfigError`**: If config is not loaded or database not found

---

## `migration_context`

Async context manager for running startup migration checks or migrations.

### Signature

```python
@asynccontextmanager
async def migration_context(
    *,
    mode: Literal["migrate", "check"] = "check",
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
) -> AsyncGenerator[None, None]
```

### Parameters

**`mode`** : `Literal["migrate", "check"]`, keyword-only, optional
- `"check"` - Read-only validation (recommended for production)
- `"migrate"` - Apply pending migrations
- Default: `"check"`

**`database`** : `str | None`, keyword-only, optional
- Database name to check/migrate
- If `None`, uses default database
- Default: `None`

**`all_databases`** : `bool`, keyword-only, optional
- If `True`, check/migrate all configured databases
- Default: `False`

**`dev`** : `bool`, keyword-only, optional
- Use dev database URL
- Default: `False`

**`strict_translation`** : `bool`, keyword-only, optional
- Enable strict SQL translation mode
- Default: `False`

**`with_backup`** : `bool`, keyword-only, optional
- Create backup before migrations (migrate mode only)
- Default: `False`

**`backup_dir`** : `str | None`, keyword-only, optional
- Directory for backups
- If `None`, uses default location
- Default: `None`

**`verbose`** : `bool`, keyword-only, optional
- Enable detailed logging
- Default: `False`

**`allow_in_production`** : `bool`, keyword-only, optional
- Allow migrate mode in production environment
- Default: `False`

**`fail_fast`** : `bool`, keyword-only, optional
- Exit immediately on failure
- If `False`, logs warning but continues
- Default: `True`

**`only_dev`** : `bool`, keyword-only, optional
- Only run in development environments
- Skipped if `ENVIRONMENT` is production
- Default: `False`

### Returns

**`AsyncGenerator[None, None]`**
- Async context manager for use in FastAPI lifespan

### Examples

```python
# Check mode (recommended)
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with migration_context(mode="check", all_databases=True):
        yield

# Migrate mode (dev only)
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with migration_context(
        mode="migrate",
        only_dev=True,
        with_backup=True,
    ):
        yield
```

### Raises

- **`RuntimeError`**: If checks fail and `fail_fast=True`
- **`ValueError`**: If `mode` is invalid

---

## `check_schema_on_startup`

Run read-only startup schema checks.

### Signature

```python
def check_schema_on_startup(
    *,
    database: str | None = None,
    all_databases: bool = False,
    dev: bool = False,
    strict_translation: bool = False,
    only_dev: bool = False,
    fail_fast: bool = True,
    verbose: bool = False,
) -> list[HealthResult]
```

### Parameters

Same as `migration_context`, except no migration-specific parameters.

### Returns

**`list[HealthResult]`**
- List of health results, one per database checked
- Each `HealthResult` contains:
  - `database`: str - Database name
  - `status`: str - "ok", "degraded", or "error"
  - `connected`: bool - Whether connection succeeded
  - `pending_migrations`: int - Number of unapplied migrations
  - `lock_active`: bool - Whether migration lock is held
  - `error`: str | None - Error message if failed

### Examples

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    results = check_schema_on_startup(all_databases=True, fail_fast=True)
    for result in results:
        print(f"{result.database}: {result.status}")
    yield
```

### Raises

- **`RuntimeError`**: If any check fails and `fail_fast=True`

---

## `migrate_on_startup`

Run migration workflow at startup.

### Signature

```python
def migrate_on_startup(
    *,
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
) -> None
```

### Parameters

Same as `migration_context` in migrate mode.

### Returns

**`None`**

### Examples

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate_on_startup(
        all_databases=True,
        with_backup=True,
        only_dev=True,
    )
    yield
```

### Raises

- **`RuntimeError`**: If migration fails and `fail_fast=True`
- **`RuntimeError`**: If in production and `allow_in_production=False`

---

## `DBWardenHealthRouter`

Creates a FastAPI `APIRouter` with health endpoints.

### Signature

```python
def DBWardenHealthRouter() -> APIRouter
```

### Returns

**`APIRouter`**
- Router with health endpoints configured
- Routes:
  - `GET /` - Overall health for all databases
  - `GET /{database_name}` - Health for specific database

### Examples

```python
from dbwarden.fastapi import DBWardenHealthRouter

app = FastAPI()
app.include_router(DBWardenHealthRouter(), prefix="/health")

# Now available:
# GET /health/ - All databases
# GET /health/primary - Specific database
```

### Response Schema

```python
{
  "status": "ok" | "degraded" | "error",
  "databases": [
    {
      "database": str,
      "status": "ok" | "degraded" | "error",
      "connected": bool,
      "pending_migrations": int,
      "lock_active": bool,
      "error": str | None
    }
  ]
}
```

### HTTP Status Codes

| Scenario | Status Code |
|----------|-------------|
| All healthy | 200 |
| Degraded (pending migrations) | 200 |
| Database unreachable | 503 |
| Database not found | 404 (per-database route only) |

---

## Type Aliases

### `SessionDep`

Recommended type alias for session dependencies:

```python
from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from dbwarden.fastapi import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session())]
```

Use in routes:

```python
@app.get("/users")
async def list_users(session: SessionDep):
    result = await session.execute(select(User))
    return result.scalars().all()
```

---

## Data Models

### `HealthResult`

Returned by `check_schema_on_startup`:

```python
@dataclass
class HealthResult:
    database: str           # Database name
    status: str             # "ok", "degraded", or "error"
    connected: bool         # Connection successful?
    pending_migrations: int # Number of unapplied migrations
    lock_active: bool       # Migration lock held?
    error: str | None       # Error message if failed
```

### `DatabaseHealth`

Pydantic model for health endpoints:

```python
class DatabaseHealth(BaseModel):
    database: str
    status: str
    connected: bool
    pending_migrations: int
    lock_active: bool
    error: str | None = None
```

### `HealthResponse`

Pydantic model for health endpoints:

```python
class HealthResponse(BaseModel):
    status: str
    databases: list[DatabaseHealth]
```

---

## Constants

### Environment Detection

DBWarden detects environment from `ENVIRONMENT` variable:

**Development environments:**
- `dev`
- `development`
- `local`
- `test`
- `testing`

**Production environments:**
- `prod`
- `production`

Used by `only_dev` and `allow_in_production` parameters.

---

## Exceptions

### `DBWardenNotInitializedError`

Raised when DBWarden config hasn't been loaded.

```python
# Fix by ensuring dbwarden.py is imported
import dbwarden  # Loads config
```

### `DBWardenDatabaseNotFoundError`

Raised when specified database name doesn't exist in config.

```python
# Fix by adding database to config
database_config(database_name="analytics", ...)
```

---

## Navigation

- **[Tutorial](tutorial/first-steps.md)** - Get started
- **[Concepts](concepts.md)** - Understand how it works
- **[Advanced](advanced/multi-database.md)** - Advanced patterns
