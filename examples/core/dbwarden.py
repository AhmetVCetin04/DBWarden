# This is the DBWarden configuration file.
# It is loaded by the CLI when you run `dbwarden` commands from this directory.
#
# The filename "dbwarden.py" is the convention — it tells the CLI
# "this is the project root." DBWarden uses a sandboxed loader to
# import it safely without conflicting with the installed package.

from dbwarden import database_config

# Each call to database_config() registers a named database target.
# The object returned (here, "primary") can be used at runtime in
# Python code — for example, to inject sessions into FastAPI routes.
primary = database_config(
    # Arbitrary name used with --database / -d on the CLI
    database_name="primary",

    # Exactly one database must have default=True. This is the one
    # used when you omit --database from CLI commands.
    default=True,

    # The SQLAlchemy backend type. DBWarden uses this to generate
    # backend-specific DDL — different SQL for SQLite vs PostgreSQL.
    database_type="sqlite",

    # The SQLAlchemy connection URL (sync driver).
    # SQLite stores the file at the given relative path.
    database_url_sync="sqlite:///./app.db",

    # Dotted paths to Python modules containing SQLAlchemy model
    # classes. DBWarden discovers them by scanning these modules
    # and their parent packages for DeclarativeBase subclasses.
    model_paths=["app"],
)
