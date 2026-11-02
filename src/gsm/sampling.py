"""Bounded, source-balanced samples for domain discovery, never factual evidence."""
from .errors import ProductError


def domain_samples(blocks,max_blocks=60,max_chars=24000):
    groups={}
    for block in blocks:groups.setdefault(block.get('source_version_id','unspecified'),[]).append(block)
    if not groups:return [],[]
    if len(groups)>max_blocks or max_chars<len(groups):raise ProductError('SAMPLE_TOO_LARGE','来源过多，请分批分析，不能静默忽略来源')
    per_blocks=max_blocks//len(groups);per_chars=max_chars//len(groups);selected=[];summary=[]
    for source,items in groups.items():
        count=min(per_blocks,len(items));indices=[round(i*(len(items)-1)/(count-1)) for i in range(count)] if count>1 else [0]
        cap=max(1,per_chars//count);sample=[]
        for index in indices:
            block=items[index];text=block['text'][:cap]
            sample.append({**block,'text':text,'text_is_excerpt':len(text)<len(block['text']),'original_characters':len(block['text'])})
        selected.extend(sample);summary.append({'source_version_id':source,'total_blocks':len(items),'sampled_blocks':len(sample),'sampled_characters':sum(len(b['text']) for b in sample)})
    return selected,summary


def extraction_samples(blocks,max_chars):
    """Small source-balanced preflight using whole blocks, not truncated table rows."""
    if not 1000<=max_chars<=80000:raise ProductError('INVALID_SAMPLE_SIZE','预览正文预算1000–80000字符')
    groups={}
    for block in blocks:groups.setdefault(block['source_version_id'],[]).append(block)
    if not groups:return [],[]
    quota=max_chars//len(groups);selected=[];summary=[]
    for source,items in groups.items():
        count=min(6,len(items));indices=[round(i*(len(items)-1)/(count-1)) for i in range(count)] if count>1 else [0]
        candidates=[items[i] for i in indices]+[item for i,item in enumerate(items) if i not in indices]
        used=0;sample=[]
        for block in candidates:
            if len(sample)>=6:break
            if block['text'].strip() and used+len(block['text'])<=quota:sample.append(block);used+=len(block['text'])
        if not sample:raise ProductError('SAMPLE_TOO_LARGE','单个来源无法在预览预算内选取完整块，请增大预算')
        selected.extend(sample);summary.append({'source_version_id':source,'total_blocks':len(items),'sampled_blocks':len(sample),'sampled_characters':used})
    return selected,summary
