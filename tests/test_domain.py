from copy import deepcopy
from decimal import Decimal
import pytest
from gsm.domain import validate_domain, Quantity, Condition
from gsm.errors import ProductError


def sample():
    return {
        'schema_version': '1', 'id': 'workplace', 'name': '企业制度',
        'types': [{'id': 'employee', 'name': '员工', 'identity': ['staff_id']}],
        'properties': [
            {'id': 'staff_id', 'name': '工号', 'subject_types': ['employee'], 'value_type': 'string'},
            {'id': 'allowance', 'name': '补贴', 'subject_types': ['employee'], 'value_type': 'quantity', 'units': ['CNY']},
        ],
        'conditions': [{'id': 'region', 'value_type': 'string'}],
    }


def test_non_automotive_domain_roundtrip():
    result = validate_domain(sample())
    assert result.types[0].identity == ['staff_id']
    assert result.model_dump(mode='json')['id'] == 'workplace'


@pytest.mark.parametrize('mutation,field', [
    (lambda d: d['properties'][0].update(subject_types=['missing']), 'subject_types'),
    (lambda d: d['properties'].append(deepcopy(d['properties'][0])), 'properties'),
    (lambda d: d['types'][0].update(identity=['unknown']), 'identity'),
    (lambda d: d.update(python='print(1)'), 'python'),
    (lambda d: d['properties'][0].update(value_type='sql'), 'value_type'),
])
def test_invalid_definitions_have_actionable_field_paths(mutation, field):
    data = sample()
    mutation(data)
    with pytest.raises(ProductError) as exc:
        validate_domain(data)
    assert exc.value.code == 'INVALID_DOMAIN'
    assert any(field in str(item['path']) for item in exc.value.details)


def test_quantity_roundtrip_preserves_decimal_precision():
    q = Quantity(value='123456789.123456789', unit='CNY')
    assert q.value == Decimal('123456789.123456789')
    assert Quantity.model_validate_json(q.model_dump_json()).value == Decimal('123456789.123456789')


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity'])
def test_quantity_rejects_nonfinite(value):
    with pytest.raises(ValueError):
        Quantity(value=value, unit='CNY')


def test_condition_tree_retains_unknown_instead_of_inventing_value():
    c = Condition.model_validate({'op': 'all', 'args': [
        {'op': 'eq', 'field': 'region', 'value': '上海'},
        {'op': 'unknown', 'field': 'temperature'},
    ]})
    assert c.args[1].op == 'unknown'
    assert c.args[1].value is None


@pytest.mark.parametrize('condition', [
    {'op': 'execute', 'value': 'rm -rf /'},
    {'op': 'all', 'args': []},
    {'op': 'eq', 'field': 'region'},
    {'op': 'in', 'field': 'region', 'value': '上海'},
    {'op': 'between', 'field': 'temperature', 'value': [20, 10]},
    {'op': 'eq', 'field': 'region', 'value': '上海', 'args': [{'op': 'unknown', 'field': 'x'}]},
])
def test_malformed_condition_is_rejected(condition):
    with pytest.raises(ValueError):
        Condition.model_validate(condition)
