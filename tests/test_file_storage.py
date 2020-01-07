import asyncio
import json
import time
import uuid
from pathlib import Path

import aiofiles
from aiohttp import web
from aiohttp_session import (
    Session,
    get_session,
    session_middleware,
)
from aiohttp_session_file import FileStorage


def create_app(handler, dirpath, max_age=None,
               key_factory=lambda: uuid.uuid4().hex):
    middleware = session_middleware(
        FileStorage(dirpath, max_age=max_age, key_factory=key_factory))
    app = web.Application(middlewares=[middleware])
    app.router.add_route('GET', '/', handler)
    return app


async def make_cookie(client, dirpath, data):
    session_data = {
        'session': data,
        'created': int(time.time())
    }
    value = json.dumps(session_data)
    key = uuid.uuid4().hex
    storage_key = ('AIOHTTP_SESSION_' + key)
    dirpath = Path(dirpath)
    filepath = dirpath / storage_key
    async with aiofiles.open(filepath, 'w') as fp:
        await fp.write(value)
    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': key})


async def make_cookie_with_bad_value(client, dirpath):
    key = uuid.uuid4().hex
    storage_key = 'AIOHTTP_SESSION_' + key
    dirpath = Path(dirpath)
    filepath = dirpath / storage_key
    filepath.touch()
    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': key})


async def load_cookie(client, dirpath):
    cookies = client.session.cookie_jar.filter_cookies(client.make_url('/'))
    key = cookies['AIOHTTP_SESSION']
    storage_key = 'AIOHTTP_SESSION_' + key.value
    dirpath = Path(dirpath)
    filepath = dirpath / storage_key
    async with aiofiles.open(filepath, 'r') as fp:
        value = await fp.read()
    value = json.loads(value)
    return value


async def test_create_new_session(aiohttp_client, dirpath):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert session.new
        assert not session._changed
        assert {} == session
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, dirpath))
    resp = await client.get('/')
    assert resp.status == 200


async def test_load_existing_session(aiohttp_client, dirpath):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert {'a': 1, 'b': 12} == session
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, dirpath))
    await make_cookie(client, dirpath, {'a': 1, 'b': 12})
    resp = await client.get('/')
    assert resp.status == 200


async def test_load_bad_session(aiohttp_client, dirpath):

    async def handler(request):
        session = await get_session(request)
        assert isinstance(session, Session)
        assert not session.new
        assert not session._changed
        assert {} == session
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, dirpath))
    await make_cookie_with_bad_value(client, dirpath)
    resp = await client.get('/')
    assert resp.status == 200


async def test_change_session(aiohttp_client, dirpath):

    async def handler(request):
        session = await get_session(request)
        session['c'] = 3
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, dirpath))
    await make_cookie(client, dirpath, {'a': 1, 'b': 2})
    resp = await client.get('/')
    assert resp.status == 200

    value = await load_cookie(client, dirpath)
    assert 'session' in value
    assert 'a' in value['session']
    assert 'b' in value['session']
    assert 'c' in value['session']
    assert 'created' in value
    assert value['session']['a'] == 1
    assert value['session']['b'] == 2
    assert value['session']['c'] == 3
    morsel = resp.cookies['AIOHTTP_SESSION']
    assert morsel['httponly']
    assert '/' == morsel['path']


async def test_clear_cookie_on_session_invalidation(aiohttp_client,
                                                    dirpath):

    async def handler(request):
        session = await get_session(request)
        session.invalidate()
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, dirpath))
    await make_cookie(client, dirpath, {'a': 1, 'b': 2})
    resp = await client.get('/')
    assert resp.status == 200

    value = await load_cookie(client, dirpath)
    assert {} == value
    morsel = resp.cookies['AIOHTTP_SESSION']
    assert morsel['path'] == '/'
    assert morsel['expires'] == "Thu, 01 Jan 1970 00:00:00 GMT"
    assert morsel['max-age'] == "0"


async def test_create_cookie_in_handler(aiohttp_client, dirpath):

    async def handler(request):
        session = await get_session(request)
        session['a'] = 1
        session['b'] = 2
        return web.Response(body=b'OK', headers={'HOST': 'example.com'})

    client = await aiohttp_client(create_app(handler, dirpath))
    resp = await client.get('/')
    assert resp.status == 200

    value = await load_cookie(client, dirpath)
    assert 'session' in value
    assert 'a' in value['session']
    assert 'b' in value['session']
    assert 'created' in value
    assert value['session']['a'] == 1
    assert value['session']['b'] == 2
    morsel = resp.cookies['AIOHTTP_SESSION']
    assert morsel['httponly']
    assert morsel['path'] == '/'
    storage_key = ('AIOHTTP_SESSION_' + morsel.value)
    dirpath = Path(dirpath)
    filepath = dirpath / storage_key
    async with aiofiles.open(filepath, 'r') as fp:
        exists = await fp.read()
    assert exists


async def test_create_new_session_if_key_doesnt_exists_in_dirpath(
        aiohttp_client, dirpath):

    async def handler(request):
        session = await get_session(request)
        assert session.new
        return web.Response(body=b'OK')

    client = await aiohttp_client(create_app(handler, dirpath))
    client.session.cookie_jar.update_cookies(
        {'AIOHTTP_SESSION': 'invalid_key'})
    resp = await client.get('/')
    assert resp.status == 200


async def test_create_storage_with_custom_key_factory(aiohttp_client,
                                                      dirpath):

    async def handler(request):
        session = await get_session(request)
        session['key'] = 'value'
        assert session.new
        return web.Response(body=b'OK')

    def key_factory():
        return 'test-key'

    client = await aiohttp_client(create_app(handler, dirpath, 8,
                                  key_factory))
    resp = await client.get('/')
    assert resp.status == 200

    assert resp.cookies['AIOHTTP_SESSION'].value == 'test-key'

    value = await load_cookie(client, dirpath)
    assert 'key' in value['session']
    assert value['session']['key'] == 'value'


async def test_file_session_fixation(aiohttp_client, dirpath):
    async def login(request):
        session = await get_session(request)
        session['k'] = 'v'
        return web.Response()

    async def logout(request):
        session = await get_session(request)
        session.invalidate()
        return web.Response()

    app = create_app(login, dirpath)
    app.router.add_route('DELETE', '/', logout)
    client = await aiohttp_client(app)
    resp = await client.get('/')
    assert 'AIOHTTP_SESSION' in resp.cookies
    evil_cookie = resp.cookies['AIOHTTP_SESSION'].value
    resp = await client.delete('/')
    assert resp.cookies['AIOHTTP_SESSION'].value == ""
    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': evil_cookie})
    resp = await client.get('/')
    assert resp.cookies['AIOHTTP_SESSION'].value != evil_cookie


async def test_load_session_dont_load_expired_session(aiohttp_client,
                                                      dirpath):
    async def handler(request):
        session = await get_session(request)
        exp_param = request.rel_url.query.get('exp', None)
        if exp_param is None:
            session['a'] = 1
            session['b'] = 2
        else:
            assert {} == session

        return web.Response(body=b'OK')

    client = await aiohttp_client(
        create_app(handler, dirpath, 2)
    )
    resp = await client.get('/')
    assert resp.status == 200

    await asyncio.sleep(5)

    resp = await client.get('/?exp=yes')
    assert resp.status == 200


async def test_file_max_age_over_30_days(aiohttp_client, dirpath):
    async def handler(request):
        session = await get_session(request)
        session['stored'] = 'TEST_VALUE'
        session.max_age = 30*24*60*60 + 1
        assert session.new
        return web.Response(body=b'OK')

    async def get_value(request):
        session = await get_session(request)
        assert not session.new
        response = session['stored']
        return web.Response(body=response.encode('utf-8'))

    app = create_app(handler, dirpath)
    app.router.add_route('GET', '/get_value', get_value)
    client = await aiohttp_client(app)

    resp = await client.get('/')
    assert resp.status == 200
    assert 'AIOHTTP_SESSION' in resp.cookies
    storage_key = 'AIOHTTP_SESSION_' + resp.cookies['AIOHTTP_SESSION'].value
    dirpath = Path(dirpath)
    filepath = dirpath / storage_key
    async with aiofiles.open(filepath, 'r') as fp:
        value = await fp.read()
    storage_value = json.loads(value)
    assert storage_value['session']['stored'] == 'TEST_VALUE'

    resp = await client.get('/get_value')
    assert resp.status == 200

    resp_content = await resp.text()
    assert resp_content == 'TEST_VALUE'


async def test_reused_expired_session_should_be_deleted(
        aiohttp_client, dirpath):
    async def handler(request):
        session = await get_session(request)
        exp_param = request.rel_url.query.get('exp', None)
        if exp_param is None:
            session['a'] = 1
            session['b'] = 2
        else:
            assert {} == session

        return web.Response(body=b'OK')

    client = await aiohttp_client(
        create_app(handler, dirpath, 2)
    )
    resp = await client.get('/')
    assert resp.status == 200

    assert 'AIOHTTP_SESSION' in resp.cookies
    key = resp.cookies['AIOHTTP_SESSION'].value
    storage_key = 'AIOHTTP_SESSION_' + key

    await asyncio.sleep(5)

    # reuse session key
    client.session.cookie_jar.update_cookies({'AIOHTTP_SESSION': key})

    resp = await client.get('/?exp=yes')
    assert resp.status == 200

    # session file and expiration file should be deleted
    dirpath = Path(dirpath)
    filepath = dirpath / storage_key
    assert not filepath.exists()
    expiration_filepath = filepath.with_suffix('.expiration')
    assert not expiration_filepath.exists()
