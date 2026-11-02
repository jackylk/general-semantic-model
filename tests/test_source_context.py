from gsm.source_context import source_context


def test_source_prompt_keeps_text_and_location_without_duplicate_raw_payload():
    text='synthetic text '*500
    block={'block_id':'b','source_version_id':'s','text':text,'span_start':0,'span_end':len(text),'locator':{'page':1,'block_index':2,'bbox':[0,0,1,1],'content':text,'cells':[{'content':text}],'text':text}}
    view=source_context(block)
    assert view['text']==text and view['locator']=={'page':1,'block_index':2,'bbox':[0,0,1,1]}
    assert view['span_start']==0 and view['span_end']==len(text)
    assert block['locator']['content']==text


def test_nonempty_caption_does_not_hide_unique_cells_or_header_relationships():
    cells=[{'row':1,'column':1,'content':'额定电压 12 V','header':'规格'}]
    view=source_context({'block_id':'b','text':'规格表','locator':{'content':'规格表','cells':cells,'headers':['规格','数值']}})
    assert view['locator']['cells']==cells
    assert view['locator']['headers']==['规格','数值']
    # Even a value mentioned in text does not prove the cell-to-header relation redundant.
    view=source_context({'block_id':'b','text':'额定电压 12 V','locator':{'cells':cells}})
    assert view['locator']['cells']==cells
