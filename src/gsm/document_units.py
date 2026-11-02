"""Generic document structure. Extracted text is not semantic completeness."""
import json
import re

NORMALIZATION_VERSION='document-units-v4'


def content_text(value):
    if isinstance(value,str):return value
    if isinstance(value,list):return ''.join(content_text(item) for item in value)
    if isinstance(value,dict):
        text=content_text(value.get('content',value.get('text','')))
        styles=value.get('styles',[])
        if 'superscript' in styles:return '^{'+text+'}'
        if 'subscript' in styles:return '_{'+text+'}'
        return text
    return ''


def layout_tables(text):
    """Conservative candidate grids, never a claim that layout implies semantics."""
    lines=text.splitlines();found=[];i=0
    while i<len(lines):
        header=re.split(r'\s{2,}',lines[i].strip())
        if len(header)<2 or not all(header) or not any(re.search(r'[^\W\d_]',x) for x in header):i+=1;continue
        rows=[header];j=i+1
        while j<len(lines):
            if not lines[j].strip():j+=1;continue
            values=re.split(r'\s{2,}',lines[j].strip())
            if len(values)!=len(header) or not all(values):break
            rows.append(values);j+=1
        if len(rows)>=3:
            found.append({'rows':rows,'header_rows':1,'structure_origin':'native_layout_inference','requires_review':True,
                'context_before':'\n'.join(lines[max(0,i-2):i]).strip(),'context_after':'\n'.join(lines[j:j+2]).strip()})
            i=j
        else:i+=1
    return found


def _table(block):
    cells=block.get('cells')
    if isinstance(cells,list) and cells and all(isinstance(row,list) for row in cells):
        if any(isinstance(cell,dict) and (cell.get('covered') or any(cell.get(key,1) not in (0,1) for key in ('col_span','row_span','colspan','rowspan'))) for row in cells for cell in row):return None
        rows=[[content_text(cell) if isinstance(cell,(dict,list)) else str(cell) for cell in row] for row in cells]
        if rows and len(rows[0])>0 and all(len(row)==len(rows[0]) for row in rows):
            count=block.get('header_rows',1)
            if not isinstance(count,int) or not 0<=count<=len(rows):return None
            return {'rows':rows,'header_rows':count,'header_origin':'declared' if 'header_rows' in block else 'first_row_convention',
                'structure_origin':'parser_cells','caption':content_text(block.get('content') or block.get('text',''))}
    return None


def normalize_document(raw,native_pages=None):
    units=[];blocks=[];pages=[]
    native={p['page']:p['text'] for p in native_pages or []}
    page_inputs=list(raw.get('pages',[]));known_pages={p['page_idx']+1 for p in page_inputs}
    page_inputs.extend({'page_idx':number-1,'blocks':[],'missing_from_parser':True} for number in native if number not in known_pages)
    for page in sorted(page_inputs,key=lambda p:p['page_idx']):
        number=page['page_idx']+1;page_units=[];known_tables=[];needs_native=bool(page.get('missing_from_parser'))
        if page.get('missing_from_parser'):page_units.append({'unit_id':f'p{number}-missing','page':number,'type':'page','status':'unresolved','issue':'PAGE_NOT_RETURNED_BY_PARSER','text':''})
        for index,block in enumerate(page.get('blocks',[])):
            kind=block.get('type','unknown');text=content_text(block.get('content') or block.get('text') or '')
            unit={'unit_id':f'p{number}-b{index}','page':number,'block_index':index,'type':kind,'status':'extracted' if text.strip() else 'unresolved','text':text,'origin':'mineru'}
            if 'bbox' in block:unit['bbox']=block['bbox']
            table=_table(block) if kind=='table' else None
            if kind=='table':
                if table:unit['table']=table;known_tables.append(table['rows']);unit['status']='extracted'
                else:unit['status']='partial' if text else 'unresolved';unit['issue']='TABLE_STRUCTURE_UNRESOLVED'
            elif kind in ('image','figure','picture'):
                unit['status']='partial' if text.strip() else 'unresolved';unit['issue']='IMAGE_ANALYSIS_NOT_RUN'
            elif not text.strip():unit['issue']='CONTENT_UNRESOLVED';needs_native|=kind in ('equation','formula')
            item={**block,'text':text,'page':number,'block_index':index,'unit_id':unit['unit_id'],'unit_type':kind}
            if text.strip():blocks.append(item)
            elif block.get('cells') and not table:
                # Keep the original structure available without inventing a grid.
                blocks.append({**item,'text':json.dumps(block['cells'],ensure_ascii=False),'representation':'parser_cells_json'})
            if table:blocks.extend(_row_blocks(table,item))
            page_units.append(unit)
        if number in native:
            for index,table in enumerate(layout_tables(native[number])):
                if table['rows'] in known_tables:continue
                unit={'unit_id':f'p{number}-native-table{index}','page':number,'type':'table','status':'partial','origin':'native_layout_inference','issue':'INFERRED_TABLE_REQUIRES_REVIEW','table':table,'text':''}
                page_units.append(unit)
                item={'page':number,'unit_id':unit['unit_id'],'unit_type':'table','representation':'native_layout_inference','requires_review':True}
                blocks.extend(_row_blocks(table,item))
        if needs_native and native.get(number,'').strip():
            # Whole-page location is honest: no invented formula-level bounding box.
            unit={'unit_id':f'p{number}-native-text','page':number,'type':'text','status':'extracted','origin':'native_text_recovery','text':native[number]}
            page_units.append(unit);blocks.append({'text':native[number],'page':number,'unit_id':unit['unit_id'],'unit_type':'text','representation':'native_text_recovery'})
        units.extend(page_units)
        pages.append({'page':number,'units':len(page_units),'unresolved_units':sum(u['status']!='extracted' for u in page_units),'text_blocks':sum(b['page']==number for b in blocks)})
    unresolved=sum(u['status']!='extracted' for u in units)
    coverage={'normalization_version':NORMALIZATION_VERSION,'status':'incomplete' if unresolved or any(p['units']==0 for p in pages) else 'text_extracted_not_semantically_complete',
        'pages':pages,'total_pages':len(pages),'total_units':len(units),'unresolved_units':unresolved,'evidence_blocks':len(blocks),'semantic_completeness':'not_proven'}
    return blocks,units,coverage


def _row_blocks(table,item):
    rows=table['rows'];head=table.get('header_rows',1);result=[]
    for index,row in enumerate(rows[head:],start=head):
        if not any(x.strip() for x in row):continue
        carrier={'caption':table.get('caption',''),'headers':rows[:head],'row':row}
        for key in ('context_before','context_after'):
            if table.get(key):carrier[key]=table[key]
        result.append({**item,'text':json.dumps(carrier,ensure_ascii=False),'unit_type':'table_row','table_row_index':index,
            'representation':table['structure_origin'],'header_origin':table.get('header_origin','native_layout_inference')})
    return result


def table_row_coverage(blocks,evidence_block_ids):
    rows={b['block_id'] for b in blocks if b.get('locator',{}).get('unit_type')=='table_row'}
    referenced=rows & set(evidence_block_ids)
    return {'total_rows':len(rows),'rows_with_supported_evidence':len(referenced),
        'unreferenced_row_ids':sorted(rows-referenced),'semantic_completeness':'not_proven',
        'note':'A cited row may still contain unextracted facts or scope errors.'}
