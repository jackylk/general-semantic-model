"""Necessary lexical grounding checks; these do not prove semantic entailment."""
import re
from decimal import Decimal

NUMBER=r'[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?'
SCALE={'':Decimal(1),'万':Decimal(10000),'亿':Decimal(100000000),'万亿':Decimal(1000000000000)}


def numbers(text):
    return {Decimal(m.group('number').replace(',',''))*SCALE[m.group('scale') or ''] for m in re.finditer(r'(?P<number>'+NUMBER+r')\s*(?P<scale>万亿|亿|万)?',text)}


def quantities(text,unit,aliases=()):
    values=set()
    for alias in [unit,*aliases]:
        pattern=r'(?P<number>'+NUMBER+r')\s*(?P<scale>万亿|亿|万)?\s*'+re.escape(alias)+r'(?![A-Za-z])'
        for match in re.finditer(pattern,text):
            values.add(Decimal(match.group('number').replace(',',''))*SCALE[match.group('scale') or ''])
    return values


def grounded(value,definition,text):
    typ=definition.value_type
    if typ=='quantity':
        if not isinstance(value,dict) or not {'value','unit'}<=set(value):return False
        return Decimal(str(value['value'])) in quantities(text,value['unit'],definition.unit_aliases.get(value['unit'],[]))
    if typ=='decimal':return Decimal(str(value)) in numbers(text)
    if typ=='list':
        item=definition.model_copy(update={'value_type':definition.item_type,'item_type':None})
        return all(grounded(v,item,text) for v in value)
    if typ=='interval':return str(value.get('start')) in text and str(value.get('end')) in text
    if typ=='boolean':return ('true' if value else 'false') in text.lower()
    return str(value) in text
