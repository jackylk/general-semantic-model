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


def test_extraction_preview_is_bounded_and_keeps_complete_selected_blocks():
    from gsm.sampling import extraction_samples
    blocks=[{'source_version_id':s,'block_id':f'{s}-{n}','text':str(n)*100,'locator':{}} for s in ('a','b') for n in range(10)]
    selected,summary=extraction_samples(blocks,1200)
    assert {b['source_version_id'] for b in selected}=={'a','b'}
    assert sum(len(b['text']) for b in selected)<=1200
    original={b['block_id']:b for b in blocks}
    assert all(b['text']==original[b['block_id']]['text'] for b in selected)
    assert len(summary)==2


def test_preview_samples_real_content_not_page_numbers_or_unreviewed_grids():
    from gsm.sampling import extraction_samples
    blocks=[]
    for i in range(100):
        kind='page_number' if i in (0,20,40,59,79,99) else 'text'
        blocks.append({'block_id':str(i),'source_version_id':'s','text':str(i) if kind=='page_number' else '独立合成正文，带有主体、范围与条件。'*5,'locator':{'unit_type':kind}})
    blocks[20]={'block_id':'unreviewed','source_version_id':'s','text':'未经确认的表格关系','locator':{'unit_type':'table_row','requires_review':True}}
    chosen,summary=extraction_samples(blocks,3000)
    assert all(b['locator']['unit_type']!='page_number' for b in chosen)
    assert all(not b['locator'].get('requires_review') for b in chosen)
    assert len(chosen)>6
    assert summary[0]['deferred_blocks']==1


def test_preview_does_not_silently_drop_source_with_only_review_only_blocks():
    from gsm.sampling import extraction_samples
    blocks=[{'block_id':'b','source_version_id':'s','text':'grid','locator':{'requires_review':True}}]
    with pytest.raises(ProductError) as exc:extraction_samples(blocks,1000)
    assert exc.value.code=='NO_AUTOMATIC_SAMPLE'
