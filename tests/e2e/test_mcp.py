import asyncio,json,os,sys
from pathlib import Path
from uuid import uuid4
import pytest
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from gsm.store import Store
from gsm.config import Settings
from gsm.auth import Principal
from gsm.credentials import write_credentials


def unpack(result):
    assert not result.isError, result.content
    return json.loads(result.content[0].text)


def test_external_mcp_contracts_and_role_boundary(tmp_path):
    kb=str(uuid4());store=Store(Settings.load());store.migrate()
    profile=tmp_path/'developer.json';write_credentials(profile,'developer',[kb])
    consumer=tmp_path/'consumer.json';write_credentials(consumer,'consumer',[kb])
    async def exercise():
        params=StdioServerParameters(command=sys.executable,args=['-m','gsm.cli','serve','--credentials',str(profile)])
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                spec=unpack(await session.call_tool('discover_spec',{}))
                assert spec['entry_phrase']=='我要开始创建知识库'
                created=unpack(await session.call_tool('create_kb',{'kb_id':kb,'name':'公开接口测试'}))
                assert created['kb_id']==kb
                bad=unpack(await session.call_tool('validate_domain',{'definition':{'sql':'SELECT secret'}}))
                assert bad['error']['code']=='INVALID_DOMAIN'
                foreign=unpack(await session.call_tool('describe_kb',{'kb_id':str(uuid4())}))
                assert foreign['error']['code']=='FORBIDDEN'
        params=StdioServerParameters(command=sys.executable,args=['-m','gsm.cli','serve','--credentials',str(consumer)])
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                names={t.name for t in (await session.list_tools()).tools}
                assert 'publish' not in names and 'register_source' not in names
                denied=await session.call_tool('publish',{'kb_id':kb,'build_id':str(uuid4())})
                assert denied.isError
                result=unpack(await session.call_tool('describe_kb',{'kb_id':kb}))
                assert result['current_release'] is None
    asyncio.run(exercise())
