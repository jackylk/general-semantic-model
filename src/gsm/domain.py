"""Declarative domain contracts: no executable extensions or industry branches."""
from decimal import Decimal
from typing import Annotated, Literal, Self
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from .errors import ProductError

Id = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')]
ValueType = Literal['string', 'boolean', 'decimal', 'enum', 'date', 'interval', 'quantity', 'object_ref', 'list']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Quantity(StrictModel):
    value: Annotated[Decimal, Field(allow_inf_nan=False)]
    unit: Annotated[str, Field(min_length=1)]


class Condition(StrictModel):
    op: Literal['eq', 'ne', 'lt', 'le', 'gt', 'ge', 'in', 'between', 'all', 'any', 'unknown']
    field: Id | None = None
    value: str | bool | Decimal | list[str | bool | Decimal] | Quantity | None = None
    args: list['Condition'] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def shape(self) -> Self:
        if self.op in ('all', 'any'):
            if not self.args or self.field is not None or self.value is not None:
                raise ValueError('all/any requires nonempty args and no field/value')
        else:
            if self.field is None or self.args:
                raise ValueError('leaf requires field and no args')
            if self.op == 'unknown':
                if self.value is not None:
                    raise ValueError('unknown cannot invent a value')
            elif self.value is None:
                raise ValueError('comparison requires value')
            elif self.op in ('in', 'between'):
                if not isinstance(self.value, list) or not self.value:
                    raise ValueError('in/between requires a nonempty list')
                if self.op == 'between':
                    if len(self.value) != 2:
                        raise ValueError('between requires two bounds')
                    try:
                        if self.value[0] > self.value[1]:
                            raise ValueError('bounds must be ascending')
                    except TypeError as exc:
                        raise ValueError('bounds must have comparable types') from exc
            elif isinstance(self.value, list):
                raise ValueError('scalar comparison cannot take a list')
        return self


class Named(StrictModel):
    id: Id
    name: Annotated[str, Field(min_length=1)]
    description: str = ''
    aliases: list[str] = Field(default_factory=list)


class ObjectType(Named):
    identity: list[Id] = Field(default_factory=list)


class TypedValue(StrictModel):
    value_type: ValueType
    units: list[str] = Field(default_factory=list)
    enum_values: list[str] = Field(default_factory=list)
    reference_types: list[Id] = Field(default_factory=list)
    item_type: Literal['string', 'boolean', 'decimal', 'date', 'quantity', 'object_ref'] | None = None

    @model_validator(mode='after')
    def value_contract(self) -> Self:
        if self.value_type == 'enum' and not self.enum_values:
            raise ValueError('enum requires enum_values')
        if self.value_type != 'enum' and self.enum_values:
            raise ValueError('enum_values only applies to enum')
        if self.units and self.value_type not in ('quantity', 'list'):
            raise ValueError('units only applies to quantity values')
        if self.value_type == 'list' and self.item_type is None:
            raise ValueError('list requires item_type')
        if self.value_type != 'list' and self.item_type is not None:
            raise ValueError('item_type only applies to list')
        is_ref = self.value_type == 'object_ref' or self.item_type == 'object_ref'
        if bool(self.reference_types) != is_ref:
            raise ValueError('object references require reference_types; other values cannot carry them')
        return self


class Property(Named, TypedValue):
    subject_types: list[Id] = Field(min_length=1)
    required_conditions: list[Id] = Field(default_factory=list)
    require_review: bool = False


class ConditionDefinition(TypedValue):
    id: Id
    name: str = ''


class Relation(Named):
    subject_types: list[Id] = Field(min_length=1)
    object_types: list[Id] = Field(min_length=1)
    required_conditions: list[Id] = Field(default_factory=list)
    require_review: bool = False


class EventRole(StrictModel):
    id: Id
    object_types: list[Id] = Field(min_length=1)
    required: bool = False


class Event(Named):
    roles: list[EventRole] = Field(min_length=1)


class Rule(Named):
    applies_to: list[Id] = Field(min_length=1)
    when: Condition
    conclusion: Annotated[str, Field(min_length=1)]
    require_review: bool = True


class Policies(StrictModel):
    extraction: str = ''
    retrieval: str = ''
    source_scope: str = ''
    # Mandatory product gates are not configurable off.
    additional_review: list[str] = Field(default_factory=list)


class DomainDefinition(Named):
    schema_version: Literal['1']
    types: list[ObjectType] = Field(min_length=1)
    properties: list[Property] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    conditions: list[ConditionDefinition] = Field(default_factory=list)
    policies: Policies = Field(default_factory=Policies)


def validate_domain(data: dict) -> DomainDefinition:
    try:
        domain = DomainDefinition.model_validate(data)
    except ValidationError as exc:
        raise ProductError('INVALID_DOMAIN', '领域定义格式不合法', [
            {'path': '.'.join(map(str, e['loc'])), 'reason': e['msg']}
            for e in exc.errors(include_input=False, include_url=False)
        ]) from None
    issues = []

    def issue(path, reason):
        issues.append({'path': path, 'reason': reason})

    for group in ('types', 'properties', 'relations', 'events', 'rules', 'conditions'):
        seen = set()
        for i, item in enumerate(getattr(domain, group)):
            if item.id in seen:
                issue(f'{group}.{i}.id', f'重复 ID: {item.id}')
            seen.add(item.id)
    types = {t.id for t in domain.types}
    props = {p.id: p for p in domain.properties}
    conditions = {c.id for c in domain.conditions}

    def refs(values, allowed, path):
        for value in values:
            if value not in allowed:
                issue(path, f'未定义的引用: {value}')

    for i, t in enumerate(domain.types):
        refs(t.identity, props, f'types.{i}.identity')
        for key in t.identity:
            if key in props and (t.id not in props[key].subject_types or props[key].value_type not in ('string', 'enum', 'decimal')):
                issue(f'types.{i}.identity', f'身份属性 {key} 必须适用于此类型且具有稳定标量值')
    for i, p in enumerate(domain.properties):
        refs(p.subject_types, types, f'properties.{i}.subject_types')
        refs(p.reference_types, types, f'properties.{i}.reference_types')
        refs(p.required_conditions, conditions, f'properties.{i}.required_conditions')
    for i, c in enumerate(domain.conditions):
        refs(c.reference_types, types, f'conditions.{i}.reference_types')
    for i, r in enumerate(domain.relations):
        refs(r.subject_types, types, f'relations.{i}.subject_types')
        refs(r.object_types, types, f'relations.{i}.object_types')
        refs(r.required_conditions, conditions, f'relations.{i}.required_conditions')
    for i, event in enumerate(domain.events):
        role_ids = [r.id for r in event.roles]
        if len(set(role_ids)) != len(role_ids):
            issue(f'events.{i}.roles', '角色 ID 重复')
        for j, role in enumerate(event.roles):
            refs(role.object_types, types, f'events.{i}.roles.{j}.object_types')
    for i, rule in enumerate(domain.rules):
        refs(rule.applies_to, types, f'rules.{i}.applies_to')
        pending = [rule.when]
        while pending:
            node = pending.pop()
            if node.field is not None:
                refs([node.field], conditions, f'rules.{i}.when.field')
            pending.extend(node.args)
    if issues:
        raise ProductError('INVALID_DOMAIN', '领域定义存在引用或身份错误', issues)
    return domain
