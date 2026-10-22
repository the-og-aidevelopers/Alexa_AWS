import asyncio
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

boto3 = pytest.importorskip("boto3")
pytest.importorskip("moto")
pytest.importorskip("jwt")

from moto import mock_aws  # noqa: E402

DOMAIN = "pillow-test.auth.us-east-1.amazoncognito.com"


@pytest.fixture
def app(monkeypatch):
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        resource.create_table(
            TableName="pillow",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        for name, value in {
            "DOSE_STORAGE": "dynamodb", "DOSE_AUTH_PROVIDER": "cognito", "AWS_ENABLED": "1", "AWS_REGION": "us-east-1",
            "COGNITO_USER_POOL_ID": "us-east-1_Test", "COGNITO_CLIENT_ID": "client123", "COGNITO_DOMAIN": DOMAIN,
            "COGNITO_REDIRECT_URI": "https://d111.cloudfront.net/api/auth/cognito-callback", "DOSE_SECRET": "s3cret",
            "DOSE_COOKIE_SECURE": "1", "DYNAMODB_TABLE": "pillow",
        }.items():
            monkeypatch.setenv(name, value)
        import importlib
        import sys

        for module in ("dose_check.server",):
            sys.modules.pop(module, None)
        server = importlib.import_module("dose_check.server")
        yield server
        # Do not leave the Cognito/DynamoDB build of the server behind for other tests.
        sys.modules.pop("dose_check.server", None)
        import dose_check

        if hasattr(dose_check, "server"):
            delattr(dose_check, "server")


def call(server, method, path, **kwargs):
    async def run():
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://d111.cloudfront.net", trust_env=False) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def test_session_tells_the_browser_where_to_sign_in(app):
    body = call(app, "GET", "/api/auth/session").json()
    assert body["authenticated"] is False and body["provider"] == "cognito"
    assert body["login_url"] == "/api/auth/cognito-login"
    assert call(app, "GET", "/api/today").status_code == 401


def test_login_redirects_to_the_hosted_ui_with_pkce(app):
    response = call(app, "GET", "/api/auth/cognito-login")
    assert response.status_code == 303
    target = urlparse(response.headers["location"])
    query = parse_qs(target.query)
    assert target.netloc == DOMAIN and target.path == "/oauth2/authorize"
    assert query["client_id"] == ["client123"] and query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["https://d111.cloudfront.net/api/auth/cognito-callback"]
    cookie = response.headers["set-cookie"].lower()
    assert "dose_oauth=" in cookie and "httponly" in cookie and "samesite=lax" in cookie and "secure" in cookie


def test_callback_rejects_a_wrong_state_and_makes_no_session(app):
    login = call(app, "GET", "/api/auth/cognito-login")
    saved = login.cookies.get("dose_oauth") or login.headers["set-cookie"].split("dose_oauth=")[1].split(";")[0]
    bad = call(app, "GET", "/api/auth/cognito-callback?code=abc&state=wrong", headers={"cookie": f"dose_oauth={saved}"})
    assert bad.status_code == 400
    assert call(app, "GET", "/api/auth/cognito-callback?code=abc&state=x").status_code == 400  # no cookie at all


def test_a_good_sign_in_creates_a_household_and_a_working_session(app, monkeypatch):
    login = call(app, "GET", "/api/auth/cognito-login")
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    saved = login.headers["set-cookie"].split("dose_oauth=")[1].split(";")[0]
    monkeypatch.setattr(app.auth, "exchange_code", lambda code, verifier: {"sub": "sub-42", "email": "ravi@example.com"})
    done = call(app, "GET", f"/api/auth/cognito-callback?code=abc&state={state}", headers={"cookie": f"dose_oauth={saved}"})
    assert done.status_code == 303 and done.headers["location"] == "/"
    session = done.headers["set-cookie"].split("dose_session=")[1].split(";")[0]
    headers = {"cookie": f"dose_session={session}"}
    me = call(app, "GET", "/api/auth/session", headers=headers).json()
    assert me["authenticated"] and me["identity"]["household_name"] == "ravi's household"
    # Their own data works end to end, and a second sign-in of the same person reuses the household.
    added = call(app, "POST", "/api/people", headers={**headers, "origin": "https://d111.cloudfront.net"}, json={"name": "Mom"})
    assert added.status_code == 200
    assert call(app, "GET", "/api/today", headers=headers).json()["people"] == ["Mom"]
    assert app.auth.directory.ensure_account("sub-42", "x", "y")["household_id"] == me["identity"]["household_id"]
    # Signing out ends the session on the server.
    assert call(app, "POST", "/api/auth/logout", headers={**headers, "origin": "https://d111.cloudfront.net"}).status_code == 200
    assert call(app, "GET", "/api/today", headers=headers).status_code == 401


def test_https_origin_through_cloudfront_is_accepted_but_other_sites_are_not(app):
    cross = call(app, "POST", "/api/auth/logout", headers={"origin": "https://evil.example"})
    assert cross.status_code == 403
