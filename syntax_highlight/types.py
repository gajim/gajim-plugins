from enum import Enum
from enum import IntEnum
from enum import unique

PLUGIN_INTERNAL_NONE_LEXER_ID = '_syntax_highlight_internal_none_type'


class MatchType(Enum):
    INLINE = 0
    MULTILINE = 1
    TEXT = 2


@unique
class LineBreakOptions(IntEnum):
    NEVER = 0
    ALWAYS = 1
    MULTILINE = 2


@unique
class CodeMarkerOptions(IntEnum):
    AS_COMMENT = 0
    HIDE = 1
