from dataclasses import dataclass, field
from pathlib import Path
import os
from dotenv import dotenv_values

@dataclass
class Settings:
    passwords: dict[str, str] = field(repr=False)
    host: str = '127.0.0.1'
    port: int = 55438
    source_root: Path | None = Path('runtime/imports')
    file_root: Path = Path('runtime/files')

    @classmethod
    def load(cls):
        cfg = {**dotenv_values('.env'), **os.environ}
        return cls(passwords={
            'owner': cfg.get('GSM_DB_PASSWORD', ''),
            'developer': cfg.get('GSM_DEVELOPER_DB_PASSWORD', ''),
            'consumer': cfg.get('GSM_CONSUMER_DB_PASSWORD', ''),
        }, host=cfg.get('GSM_DB_HOST', '127.0.0.1'), port=int(cfg.get('GSM_DB_PORT', 55438)),
            source_root=Path(cfg.get('GSM_SOURCE_ROOT', 'runtime/imports')).resolve(),
            file_root=Path(cfg.get('GSM_FILE_ROOT', 'runtime/files')).resolve())
