"""Source presentation for models; original parse/evidence stays immutable."""
import json


def redundant_text(value,text):
    if isinstance(value,str):return value==text
    if isinstance(value,dict) and len(value)==1 and set(value)<={'content','text'}:
        return redundant_text(next(iter(value.values())),text)
    if isinstance(value,list) and len(value)==1:return redundant_text(value[0],text)
    # Exact serialization in the text proves structure is present, unlike matching cell values.
    return isinstance(value,(dict,list)) and json.dumps(value,ensure_ascii=False) in text


def source_context(block):
    text=block.get('text','');locator=dict(block.get('locator',{}))
    for key in ('content','text','cells'):
        if key in locator and redundant_text(locator[key],text):locator.pop(key)
    # Unknown fields, unique cell values and row/header associations must remain available.
    result={key:block[key] for key in ('block_id','source_version_id','text','span_start','span_end') if key in block}
    result['locator']=locator
    return result
