import pytest

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")

from moto import mock_aws  # noqa: E402

from dose_check.db import Store  # noqa: E402
from dose_check.dynamo import DynamoStore  # noqa: E402


@pytest.fixture
def table():
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        resource.create_table(
            TableName="pillow",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield DynamoStore("pillow", region="us-east-1", household_id=1)


def test_people_and_schedules_behave_like_the_sqlite_store(table, tmp_path):
    sqlite = Store(tmp_path / "x.sqlite")
    for store in (table, sqlite):
        assert store.add_person("Raj") == {"name": "Raj", "created": True}
        assert store.add_person("raj") == {"name": "Raj", "created": False}
        first = store.add_schedule("Mom", "lisinopril", "20:00", days="0,4")
        store.add_schedule("Mom", "lisinopril", "08:00")
        assert store.list_people() == ["Mom", "Raj"]
        assert [(r["time_local"], r["days"]) for r in store.list_schedules()] == [("08:00", "0,1,2,3,4,5,6"), ("20:00", "0,4")]
        assert store.find_person("MOM") == "Mom"
        assert store.update_schedule(first["id"], "lisinopril 10mg", "21:00", "5,6")
        assert not store.update_schedule(9999, "x", "21:00", "5")
        assert {r["time_local"] for r in store.list_schedules()} == {"08:00", "21:00"}


def test_logs_are_per_day_and_cleared_by_person(table):
    mom = table.add_schedule("Mom", "aspirin", "08:00")
    raj = table.add_schedule("Raj", "dopamine", "08:00")
    table.upsert_log(mom["id"], "2026-10-05", "taken", "", "now")
    table.upsert_log(mom["id"], "2026-10-06", "skipped", "dizzy", "now")
    table.upsert_log(raj["id"], "2026-10-06", "taken", "", "now")
    assert table.get_log(mom["id"], "2026-10-06")["reason"] == "dizzy"
    assert table.get_log(mom["id"], "2026-10-07") is None
    assert table.clear_logs("2026-10-06", "Mom") == 1
    assert table.get_log(raj["id"], "2026-10-06")["status"] == "taken"
    assert table.clear_logs() == 2
    table.upsert_log(9999, "2026-10-05", "taken", "", "now")  # unknown schedule is ignored
    assert table.clear_logs() == 0


def test_deleting_removes_logs_and_other_households_are_isolated(table):
    mine = table.add_schedule("Mom", "aspirin", "08:00")
    table.upsert_log(mine["id"], "2026-10-05", "taken", "", "now")
    other = table.scoped(2)
    theirs = other.add_schedule("Mom", "aspirin", "08:00")
    assert other.list_people() == ["Mom"] and len(table.list_schedules()) == 1
    assert not other.delete_schedule(mine["id"])         # cannot touch another household's dose
    other.upsert_log(mine["id"], "2026-10-05", "skipped", "", "now")
    assert table.get_log(mine["id"], "2026-10-05")["status"] == "taken"
    assert table.delete_schedule(mine["id"]) and table.get_log(mine["id"], "2026-10-05") is None
    assert table.delete_person("mom") is True             # the person record remains until removed
    assert table.delete_person("mom") is False
    assert other.delete_person("Mom") and other.list_people() == [] and theirs["id"] != mine["id"]


def test_the_first_cognito_sign_in_creates_one_household(table):
    first = table.ensure_account("sub-1", "a@example.com", "A's household")
    again = table.ensure_account("sub-1", "a@example.com", "different name")
    other = table.ensure_account("sub-2", "b@example.com", "B's household")
    assert first == again and other["household_id"] != first["household_id"]
    assert table.account_for_sub("nobody") is None


def test_sessions_expire(table):
    import time

    table.save_session("hash", "sub-1", int(time.time()) + 60)
    assert table.session_sub("hash") == "sub-1"
    table.save_session("old", "sub-1", int(time.time()) - 1)
    assert table.session_sub("old") is None
    table.delete_session("hash")
    assert table.session_sub("hash") is None
