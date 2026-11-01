"""Necessary lexical grounding checks; these do not prove semantic entailment."""
import re
from decimal import Decimal
from html.parser import HTMLParser

NUMBER=r'[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?'
SCALE={'':Decimal(1),'万':Decimal(10000),'亿':Decimal(100000000),'万亿':Decimal(1000000000000)}


class _EvidenceText(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.parts.append(' |ROW| ')
        elif tag in ('td','th','br','p','div'):self.parts.append(' ')
    def handle_endtag(self,tag):
        if tag=='tr':self.parts.append(' |ROW| ')
        elif tag in ('td','th','p','div'):self.parts.append(' ')
    def handle_data(self,data):self.parts.append(data)


def evidence_text(text):
    if '<' not in text:return text
    parser=_EvidenceText();parser.feed(text);parser.close()
    return ''.join(parser.parts)


def numbers(text):
    text=evidence_text(text)
    return {Decimal(m.group('number').replace(',',''))*SCALE[m.group('scale') or ''] for m in re.finditer(r'(?P<number>'+NUMBER+r')\s*(?P<scale>万亿|亿|万)?',text)}


def quantities(text,unit,aliases=()):
    text=evidence_text(text)
    values=set()
    for alias in [unit,*aliases]:
        pattern=r'(?P<number>'+NUMBER+r')\s*(?P<scale>万亿|亿|万)?\s*'+re.escape(alias)+r'(?:max|min|typ|MAX|MIN|TYP)?(?![A-Za-z])'
        for match in re.finditer(pattern,text):
            values.add(Decimal(match.group('number').replace(',',''))*SCALE[match.group('scale') or ''])
    return values


def grounded(value,definition,text):
    text=evidence_text(text)
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
