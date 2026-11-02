import pytest
from gsm.errors import ProductError


def test_domain_analysis_samples_every_source_and_spreads_across_its_blocks():
    from gsm.sampling import domain_samples
    blocks=[{'source_version_id':str(s),'block_id':f'{s}-{i}','text':'text '+str(i),'locator':{'page':i+1}} for s in range(6) for i in range(100)]
    selected,summary=domain_samples(blocks)
    assert {b['source_version_id'] for b in selected}=={str(s) for s in range(6)}
    assert len(selected)<=60 and sum(len(b['text']) for b in selected)<=24000
    assert all(any(b['block_id']==f'{s}-99' for b in selected) for s in range(6))
    assert len(summary)==6 and all(x['total_blocks']==100 for x in summary)


def test_sampling_marks_excerpt_and_never_drops_a_source_silently():
    from gsm.sampling import domain_samples
    blocks=[{'source_version_id':str(i),'block_id':str(i),'text':'x'*10000} for i in range(6)]
    samples,_=domain_samples(blocks)
    assert len(samples)==6 and all(b['text_is_excerpt'] for b in samples)
    assert sum(len(b['text']) for b in samples)<=24000
    with pytest.raises(ProductError):domain_samples(blocks,max_blocks=3)
