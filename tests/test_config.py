from pathlib import Path
from gsm.config import Settings


def test_default_file_store_is_outside_product_directory():
    settings=Settings(passwords={})
    assert not settings.file_root.resolve().is_relative_to(Path.cwd().resolve())
    assert settings.source_root is None


def test_load_without_source_configuration_does_not_guess_an_import_directory(monkeypatch):
    monkeypatch.setattr('gsm.config.dotenv_values',lambda path:{})
    monkeypatch.delenv('GSM_SOURCE_ROOT',raising=False)
    monkeypatch.delenv('GSM_FILE_ROOT',raising=False)
    settings=Settings.load()
    assert settings.source_root is None
    assert not settings.file_root.resolve().is_relative_to(Path.cwd().resolve())
