try:
    from schemap import auto_schema as _schemap_auto_schema
    auto_schema = _schemap_auto_schema
except ImportError:
    auto_schema = None

__all__ = ["auto_schema"]
