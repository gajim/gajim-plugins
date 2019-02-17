from enum import Enum, IntEnum, unique

class MatchType(Enum):
    INLINE      = 0
    MULTILINE   = 1
    TEXT        = 2

@unique
class LineBreakOptions(IntEnum):
    NEVER       = 0
    ALWAYS      = 1
    MULTILINE   = 2

@unique
class CodeMarkerOptions(IntEnum):
    AS_COMMENT  = 0
    HIDE        = 1


