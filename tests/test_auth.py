import time
from types import SimpleNamespace

import anyio
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.requests import Request

from dose_check.auth import Auth, COOKIE
from dose_check.db import Store
from dose_check.mcp_client import call_tool
from test_server import server


@pytest.mark.parametrize('server', ['local'], indirect=True)
def test_local_login_isolates_rest_and_mcp(server):
    with httpx.Client(base_url=server, trust_env=False) as a, httpx.Client(base_url=server, trust_env=False) as b:
        assert a.get('/').status_code == 303
        assert a.get('/api/today').status_code == 401
        assert a.post('/mcp', json={}).status_code == 401
        assert a.post('/api/auth/register', json={'email':'a@example.com','password':'short','household_name':'A'}).status_code == 400
        for client, email, name in [(a, 'a@example.com', 'Family A'), (b, 'b@example.com', 'Family B')]:
            response = client.post('/api/auth/register', json={'email':email,'password':'long-password-123','household_name':name})
            assert response.status_code == 200, response.text
            assert 'HttpOnly' in response.headers['set-cookie']
            assert 'SameSite=strict' in response.headers['set-cookie']
            assert client.get('/api/today').json()['doses'] == []
        added = a.post('/api/schedules', json={'person_name':'Mom','dose_label':'test medicine','time_local':'08:00','household_id':b.get('/api/auth/session').json()['identity']['household_id']})
        assert added.status_code == 201
        schedule_id = added.json()['id']
        assert b.get('/api/schedules').json()['schedules'] == []
        assert b.delete(f'/api/schedules/{schedule_id}').status_code == 404
        reply = a.post('/api/talk', json={'utterance':'I took the morning one'}, timeout=15)
        assert reply.status_code == 200, reply.text
        assert reply.json()['result']['ok']
        async def direct():
            return await call_tool(server+'/mcp', 'summarize_day', {}, headers={'Cookie':f'{COOKIE}={b.cookies[COOKIE]}'})
        result, protocol = anyio.run(direct)
        assert result['ok']
        assert protocol >= '2025-11-25'
        assert b.post('/api/logs/reset').status_code == 200
        assert a.get('/api/today').json()['doses'][0]['state'] == 'taken'
        assert a.post('/api/auth/logout', headers={'Origin':'https://evil.example'}).status_code == 403
        assert a.get('/api/today').status_code == 200
        assert a.post('/api/auth/logout').status_code == 200
        assert a.get('/api/today').status_code == 401
        assert a.post('/api/auth/login', json={'email':'a@example.com','password':'wrong-password-123'}).status_code == 400
        assert a.post('/api/auth/login', json={'email':'a@example.com','password':'long-password-123'}).status_code == 200
        assert a.get('/').status_code == 200


def test_store_cannot_read_write_or_clear_another_household(tmp_path):
    store = Store(tmp_path/'store.sqlite')
    a, b = store.scoped(2), store.scoped(3)
    schedule = a.add_schedule('A', 'med', '08:00')['id']
    b.upsert_log(schedule,'2026-10-05','taken','','now')
    assert a.get_log(schedule,'2026-10-05') is None
    a.upsert_log(schedule,'2026-10-05','taken','','now')
    assert b.get_log(schedule,'2026-10-05') is None
    b.clear_logs()
    assert not b.delete_schedule(schedule)
    assert a.get_log(schedule,'2026-10-05')['status'] == 'taken'


def test_local_session_expires_and_password_is_hashed(tmp_path, monkeypatch):
    monkeypatch.setenv('DOSE_AUTH_PROVIDER','local')
    auth = Auth(Store(tmp_path/'accounts.sqlite'))
    account = auth.create({'email':'a@example.com','password':'long-password-123','household_name':'A'})
    with auth.store.connect() as conn:
        assert conn.execute('SELECT password FROM accounts').fetchone()['password'] != 'long-password-123'
    token = auth.session(account)
    request = Request({'type':'http','headers':[(b'cookie',f'{COOKIE}={token}'.encode())]})
    assert auth.identity(request)['household_id'] != 1
    with auth.store.connect() as conn:
        conn.execute('UPDATE sessions SET expires=0')
        assert conn.execute('SELECT token_hash FROM sessions').fetchone()['token_hash'] != token
    assert auth.identity(request) is None


@pytest.mark.parametrize('changes', [{}, {'exp':1}, {'token_use':'id'}, {'client_id':'other'}, {'iss':'https://evil.example'}, {'sub':None}, {'sub':'unmapped'}])
def test_cognito_verifier_offline(tmp_path, monkeypatch, changes):
    monkeypatch.setenv('AWS_ENABLED','1')
    monkeypatch.setenv('DOSE_AUTH_PROVIDER','cognito')
    monkeypatch.setenv('AWS_REGION','us-east-1')
    monkeypatch.setenv('COGNITO_USER_POOL_ID','us-east-1_example')
    monkeypatch.setenv('COGNITO_CLIENT_ID','trusted-client')
    auth = Auth(Store(tmp_path/'cognito.sqlite'))
    key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    auth.jwks = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key()))
    with auth.store.connect() as conn:
        conn.execute("INSERT INTO accounts(email,password,household_id,cognito_sub) VALUES ('a@example.com','',1,'trusted-sub')")
    claims = {'sub':'trusted-sub','exp':int(time.time())+60,'iat':int(time.time()),'iss':auth.issuer,'client_id':'trusted-client','token_use':'access', **changes}
    token = jwt.encode(claims,key,algorithm='RS256')
    request = Request({'type':'http','headers':[(b'authorization',f'Bearer {token}'.encode())]})
    assert bool(auth.identity(request)) == (not changes)
    wrong = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    token = jwt.encode(claims,wrong,algorithm='RS256')
    assert auth.identity(Request({'type':'http','headers':[(b'authorization',f'Bearer {token}'.encode())]})) is None


def test_cognito_disabled_without_aws_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv('AWS_ENABLED','0')
    monkeypatch.setenv('DOSE_AUTH_PROVIDER','cognito')
    with pytest.raises(ValueError, match='AWS_ENABLED'):
        Auth(Store(tmp_path/'offline.sqlite'))
