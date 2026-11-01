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
