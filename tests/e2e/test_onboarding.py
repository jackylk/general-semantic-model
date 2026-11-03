from uuid import uuid4
import pytest
from gsm.config import Settings
from gsm.store import Store
from gsm.auth import Principal
from gsm.onboarding import OnboardingService
from gsm.errors import ProductError


def test_onboarding_restores_confirmed_choices_and_rejects_stale_updates():
    store=Store(Settings.load());store.migrate()
    kb=str(uuid4());p=Principal('developer',frozenset([kb]));store.create_kb(p,kb,'引导')
    service=OnboardingService(store)
    first=service.get(p,kb)
    assert first['next_step']=='了解用途和代表性问题'
    saved=service.save(p,kb,{'purpose':'设备维护','questions':['什么时候应停止使用？'],'choices':{'identity':'按序号区分设备'}},expected_revision=0)
    restored=OnboardingService(store).get(p,kb)
    assert restored['state']['choices']['identity']=='按序号区分设备'
    assert restored['revision']==saved['revision']
    with pytest.raises(ProductError):service.save(p,kb,{'purpose':'other'},expected_revision=0)
    with pytest.raises(ProductError):service.get(Principal('consumer',frozenset([kb])),kb)


def test_unresolved_can_record_plain_language_blockers_and_reports_bad_fields():
    from uuid import uuid4
    store=Store(Settings.load());store.migrate();kb=str(uuid4());p=Principal('developer',frozenset([kb]));store.create_kb(p,kb,'state')
    service=OnboardingService(store)
    saved=service.save(p,kb,{'unresolved':['资料预览超过单批限制，需要分批']},0)
    assert saved['state']['unresolved']==['资料预览超过单批限制，需要分批']
    with pytest.raises(ProductError) as exc:service.save(p,kb,{'made_up_field':'x'},1)
    assert any('made_up_field' in i['path'] for i in exc.value.details)


def test_guidance_requires_topic_selection_and_records_simulated_provenance():
    store=Store(Settings.load());store.migrate();kb=str(uuid4());p=Principal('developer',frozenset([kb]));store.create_kb(p,kb,'guided')
    service=OnboardingService(store)
    step=service.save(p,kb,{'purpose':'设备资料问答','questions':['适用条件是什么？'],'source_version_ids':['synthetic-source']},0)
    assert step['next_step']=='推荐抽取主题并由用户选择'
    step=service.save(p,kb,{'topics':['运行边界与异常处理'],'topic_selection_origin':'simulated_user'},1)
    assert step['state']['topic_selection_origin']=='simulated_user'
    assert step['next_step']=='分析样本，提出领域草案和少量业务选择'
    step=service.save(p,kb,{'topics':['新主题']},2)
    assert step['state']['topic_selection_origin']=='unconfirmed'
    assert step['next_step']=='推荐抽取主题并由用户选择'


def test_topic_change_archives_old_choices_instead_of_reusing_them():
    store=Store(Settings.load());store.migrate();kb=str(uuid4());p=Principal('developer',frozenset([kb]));store.create_kb(p,kb,'topic-change')
    service=OnboardingService(store)
    service.save(p,kb,{'topics':['合成主题A'],'topic_selection_origin':'user','choices':{'identity':'按序号'}},0)
    changed=service.save(p,kb,{'topics':['合成主题B']},1)
    assert changed['state']['choices']=={}
    assert changed['state']['choice_history'][-1]['choices']=={'identity':'按序号'}
    assert changed['state']['topic_selection_origin']=='unconfirmed'
