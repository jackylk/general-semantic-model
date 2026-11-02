import hashlib,json
import pytest
from tokenizers import Tokenizer,models,pre_tokenizers
from gsm.errors import ProductError


def fixture_file(tmp_path):
    tokenizer=Tokenizer(models.WordLevel({'[UNK]':0,'hello':1,'world':2},unk_token='[UNK]'))
    tokenizer.pre_tokenizer=pre_tokenizers.Whitespace();tokenizer.add_special_tokens(['<CONTROL>'])
    path=tmp_path/'tokenizer.json';path.write_text(tokenizer.to_str());return path


def test_local_token_count_removes_added_control_tokens_and_checks_hash(tmp_path):
    from gsm.adapters.token_budget import TokenBudget
    path=fixture_file(tmp_path);digest=hashlib.sha256(path.read_bytes()).hexdigest();counter=TokenBudget(path,digest)
    assert counter.count_text('hello world')==2
    assert counter.count_text('<CONTROL>')>1
    assert counter.bound('hello world','')>=2+256
    with pytest.raises(ProductError):TokenBudget(path,'0'*64)


def test_llm_uses_optional_local_counter_without_sending_credentials_to_it(tmp_path):
    from gsm.adapters.llm import LLM
    path=fixture_file(tmp_path)
    model=LLM('https://example.invalid','test','private',tokenizer_path=path)
    assert model.input_token_bound('hello world','')<len('hello world'.encode())+256
    assert model.token_budget_mode=='local_tokenizer_with_margin'
