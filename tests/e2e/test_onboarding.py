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
