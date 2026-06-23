from __future__ import annotations

from dataclasses import dataclass

from dbwarden.databases.sqlite.field import SqFieldSpec, field
from dbwarden.schema._meta import SqFieldMeta

import sys as _sys
sq = _sys.modules[__name__]


@dataclass
class SqTableSpec:
    without_rowid: bool = False
    strict: bool = False


__all__ = [
    "SqFieldMeta",
    "SqFieldSpec",
    "SqTableSpec",
    "field",
    "sq",
]
