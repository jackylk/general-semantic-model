from dataclasses import dataclass
from .errors import ProductError

@dataclass(frozen=True)
class Principal:
    role: str
    kb_ids: frozenset[str]

    def require(self, kb_id: str, write: bool = False):
        if self.role not in ('developer', 'consumer') or kb_id not in self.kb_ids or (write and self.role != 'developer'):
            raise ProductError('FORBIDDEN', '当前身份没有此操作的授权')
