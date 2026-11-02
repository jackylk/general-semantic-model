import copy
from gsm.adapters.mineru import Parser


def test_units_keep_unread_media_without_inventing_text():
    raw={'pages':[{'page_idx':0,'blocks':[{'type':'image','bbox':[0,0,1,1],'content':''},{'type':'equation','content':''},{'type':'text','content':'Readable text'}]}]}
    original=copy.deepcopy(raw);parsed=Parser.from_middle(raw,'test')
    assert len(parsed.units)==3
    assert [u['status'] for u in parsed.units]==['unresolved','unresolved','extracted']
    assert parsed.coverage['unresolved_units']==2
    assert parsed.coverage['status']=='incomplete'
    assert len(parsed.blocks)==1 and parsed.raw==original and raw==original


def test_caption_does_not_hide_table_rows_or_headers():
    raw={'pages':[{'page_idx':0,'blocks':[{'type':'table','content':'Measured power','cells':[['Temperature (C)','Power (W)'],['20','10.25'],['30','12.50']]}]}]}
    parsed=Parser.from_middle(raw,'test')
    rows=[b for b in parsed.blocks if b.get('unit_type')=='table_row']
    assert len(rows)==2
    assert 'Temperature (C)' in rows[1]['text'] and '30' in rows[1]['text']
    assert 'Power (W)' in rows[1]['text'] and '12.50' in rows[1]['text']
    assert rows[1]['table_row_index']==2
    assert parsed.units[0]['table']['rows'][2]==['30','12.50']


def test_superscript_styles_are_explicit_in_text_and_raw_is_kept():
    raw={'pages':[{'page_idx':2,'blocks':[{'type':'text','content':[{'content':'x'},{'content':'2','styles':['superscript']},{'content':' H'},{'content':'2','styles':['subscript']},{'content':'O'}]}]}]}
    parsed=Parser.from_middle(raw,'test')
    assert parsed.blocks[0]['text']=='x^{2} H_{2}O'
    assert parsed.units[0]['page']==3


def test_empty_only_document_has_actionable_coverage_in_error():
    import pytest
    from gsm.errors import ProductError
    with pytest.raises(ProductError) as e:Parser.from_middle({'pages':[{'page_idx':0,'blocks':[{'type':'image'}]}]},'test')
    assert e.value.code=='NO_CONTENT'
    assert e.value.details[0]['coverage']['unresolved_units']==1


def test_layout_table_recovery_requires_consistent_rows_and_preserves_scope():
    from gsm.document_units import layout_tables
    tables=layout_tables('Table 1: power\nTemperature (C)       Power (W)\n20                    10.25\n30                    12.50\nOnly dry conditions.\n')
    assert len(tables)==1
    assert tables[0]['rows']==[['Temperature (C)','Power (W)'],['20','10.25'],['30','12.50']]
    assert 'Only dry conditions.' in tables[0]['context_after']
    assert layout_tables('a     b\n1\n2     3\n')==[]


def test_native_supplement_recovers_rows_and_symbols_but_keeps_formula_gap():
    raw={'pages':[{'page_idx':0,'blocks':[{'type':'text','content':'Table 1'},{'type':'equation','content':''}]}]}
    native=[{'page':1,'text':'Temperature (C)       Power (W)\n20                    10.25\n30                    12.50\nSymbols: α β γ ≤ ≥ ±'}]
    p=Parser.from_middle(raw,'test',native_pages=native)
    assert any(b.get('unit_type')=='table_row' and '12.50' in b['text'] for b in p.blocks)
    assert any('α β γ ≤ ≥ ±' in b['text'] for b in p.blocks)
    assert p.coverage['status']=='incomplete'
    assert any(u['type']=='equation' and u['status']=='unresolved' for u in p.units)


def test_caption_only_table_is_reported_as_unstructured():
    p=Parser.from_middle({'pages':[{'page_idx':0,'blocks':[{'type':'table','content':'Caption only'}]}]},'test')
    assert p.coverage['unresolved_units']==1
    assert p.units[0]['issue']=='TABLE_STRUCTURE_UNRESOLVED'


def test_table_rows_cannot_be_silently_split_to_fit_batch():
    import pytest
    from gsm.pipeline import split_batches
    from gsm.errors import ProductError
    with pytest.raises(ProductError) as e:
        split_batches([{'source_version_id':'s','block_id':'b','text':'x'*1100,'locator':{'unit_type':'table_row'}}],1000)
    assert e.value.code=='STRUCTURED_UNIT_TOO_LARGE'


def test_header_units_travel_with_values_without_changing_source_cells():
    raw={'pages':[{'page_idx':0,'blocks':[{'type':'table','cells':[['Temperature (C)','Power (W)'],['30','12.50']]}]}]}
    p=Parser.from_middle(raw,'test');row=next(b for b in p.blocks if b.get('unit_type')=='table_row')
    assert 'Temperature (C)' in row['text'] and 'Power (W)' in row['text']
    assert 'quantity_text' not in row['text']
    assert p.units[0]['table']['rows'][1]==['30','12.50']


def test_row_evidence_coverage_does_not_claim_semantic_completeness():
    from gsm.document_units import table_row_coverage
    blocks=[{'block_id':'r1','locator':{'unit_type':'table_row'}},{'block_id':'r2','locator':{'unit_type':'table_row'}},{'block_id':'t','locator':{}}]
    report=table_row_coverage(blocks,['r1','t'])
    assert report['total_rows']==2 and report['unreferenced_row_ids']==['r2']
    assert report['semantic_completeness']=='not_proven'


def test_native_recovery_does_not_skip_a_second_table_on_the_same_page():
    raw={'pages':[{'page_idx':0,'blocks':[{'type':'table','cells':[['A','B'],['1','2']]},{'type':'table','content':'Second table'}]}]}
    native=[{'page':1,'text':'Temperature (C)       Power (W)\n20                    10.25\n30                    12.50'}]
    p=Parser.from_middle(raw,'test',native_pages=native)
    assert any(b.get('unit_type')=='table_row' and '12.50' in b['text'] for b in p.blocks)


def test_header_qualifiers_are_not_rewritten_as_measurement_units():
    raw={'pages':[{'page_idx':0,'blocks':[{'type':'table','cells':[['Power (maximum)'],['12.50']]}]}]}
    p=Parser.from_middle(raw,'test');row=next(b for b in p.blocks if b.get('unit_type')=='table_row')
    assert '12.50 maximum' not in row['text'] and 'quantity_text' not in row['text']


def test_parser_representation_cannot_be_mistaken_for_fact_provenance():
    import pytest
    from pydantic import ValidationError
    from gsm.build import Candidate
    with pytest.raises(ValidationError):Candidate(kind='assertion',provenance='table_row')
    assert Candidate(kind='assertion',provenance='source_statement').provenance=='source_statement'


def test_image_caption_is_not_claimed_as_complete_image_extraction():
    p=Parser.from_middle({'pages':[{'page_idx':0,'blocks':[{'type':'image','content':'A diagram caption'}]}]},'test')
    assert p.coverage['status']=='incomplete'
    assert p.units[0]['issue']=='IMAGE_ANALYSIS_NOT_RUN'


def test_native_page_inventory_reveals_pages_omitted_by_parser():
    p=Parser.from_middle({'pages':[{'page_idx':0,'blocks':[{'type':'text','content':'p1'}]}]},'test',native_pages=[{'page':1,'text':'p1'},{'page':2,'text':'p2'}])
    assert p.coverage['total_pages']==2 and p.coverage['status']=='incomplete'
    assert any(u.get('issue')=='PAGE_NOT_RETURNED_BY_PARSER' for u in p.units)
    assert any(b['page']==2 and b['text']=='p2' for b in p.blocks)


def test_unsupported_merged_cells_are_not_silently_flattened_into_aligned_rows():
    raw={'pages':[{'page_idx':0,'blocks':[{'type':'table','cells':[[{'content':'Voltage','col_span':2},''],['12','24']]}]}]}
    p=Parser.from_middle(raw,'test')
    assert p.coverage['status']=='incomplete'
    assert not any(b.get('unit_type')=='table_row' for b in p.blocks)


def test_automatic_extraction_defers_review_only_derivatives_without_losing_units():
    from gsm.pipeline import automatic_blocks
    blocks=[{'block_id':'original','text':'original source','locator':{}},{'block_id':'derived','text':'candidate row','locator':{'requires_review':True}},{'block_id':'structured','text':'known grid row','locator':{'unit_type':'table_row'}}]
    selected,deferred=automatic_blocks(blocks)
    assert [x['block_id'] for x in selected]==['original','structured']
    assert [x['block_id'] for x in deferred]==['derived']
    assert len(blocks)==3 and blocks[1]['text']=='candidate row'
