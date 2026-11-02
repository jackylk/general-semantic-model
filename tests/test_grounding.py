import pytest
from gsm.domain import Property
from gsm.grounding import grounded


def voltage():
    return Property(id='maximum_voltage',name='最大电压',subject_types=['module'],value_type='quantity',units=['V'])


@pytest.mark.parametrize('quote',[
    'Each reference design manages up to 18 cells (100Vmax).',
    '<table><tr><td>Maximum voltage</td><td>100</td><td>V</td></tr></table>',
])
def test_voltage_max_suffix_and_same_row_html_cells_are_grounded(quote):
    assert grounded({'value':'100','unit':'V'},voltage(),quote)


def test_voltage_does_not_match_va_or_cross_table_rows():
    definition=voltage();value={'value':'100','unit':'V'}
    assert not grounded(value,definition,'rating 100VA')
    assert not grounded(value,definition,'<table><tr><td>unrelated count</td><td>100</td></tr><tr><td>V</td><td>10</td></tr></table>')


def test_text_condition_allows_layout_whitespace_without_crossing_table_rows():
    from types import SimpleNamespace
    definition=SimpleNamespace(value_type='string')
    phrase='time or mileage, whichever comes first'
    assert grounded(phrase,definition,'Warranty period (time or mileage, whichever\ncomes first)')
    assert not grounded(phrase,definition,'<table><tr><td>time or mileage, whichever</td></tr><tr><td>comes first</td></tr></table>')
    assert not grounded(phrase,definition,'time or mileage, whichever comes last')


def test_quote_newline_mapping_preserves_actual_source_offsets():
    from gsm.grounding import locate_quote
    text='prefix: Warranty period\nwhichever comes first. end'
    span=locate_quote(text,'Warranty period\r\nwhichever comes first.')
    assert span and text[span[0]:span[1]]=='Warranty period\nwhichever comes first.'
    assert locate_quote(text,'Warranty period whichever comes first.') is None
    reverse='x:A\r\nB!';span=locate_quote(reverse,'A\nB')
    assert reverse[span[0]:span[1]]=='A\r\nB'


def test_structured_row_units_must_match_the_same_column_header():
    from decimal import Decimal
    import json
    from gsm.grounding import quantities
    row=json.dumps({'headers':[['Temperature (C)','Power (W)']],'row':['30','12.50']})
    assert quantities(row,'W')=={Decimal('12.50')}
    assert quantities(row,'C')=={Decimal('30')}
    assert not quantities(row,'V')
    qualifier=json.dumps({'headers':[['Power (maximum)']],'row':['12.50']})
    assert not quantities(qualifier,'W')
