"""DynamoDB storage with the same methods as the SQLite `Store`.

One table, on-demand billing. Keys:

    pk = H#<household>   sk = P#<name, lower case>            a person
    pk = H#<household>   sk = S#<schedule id>                 a medicine time
    pk = H#<household>   sk = L#<day>#<schedule id>           a taken/skipped entry
    pk = META            sk = SEQ#<name>                      id counters
    pk = SUB#<cognito>   sk = ACCOUNT                         sign-in -> household
    pk = SESSION#<hash>  sk = SESSION                         a browser session (expires with TTL)

Household access is checked on every call, the same way the SQLite store scopes by household.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from dose_check.logic import ALL_DAYS


class DynamoStore:
    def __init__(
        self,
        table_name: str = "pillow",
        region: str | None = None,
        endpoint_url: str | None = None,
        household_id: int = 1,
        resource: Any = None,
    ) -> None:
        import boto3

        self.household_id = household_id
        self.table_name = table_name
        self._resource = resource or boto3.resource("dynamodb", region_name=region, endpoint_url=endpoint_url)
        self.table = self._resource.Table(table_name)

    # -- scoping ---------------------------------------------------------------------------

    def scoped(self, household_id: int) -> "DynamoStore":
        return DynamoStore(self.table_name, household_id=int(household_id), resource=self._resource)

    def seed_if_empty(self) -> None:  # nothing is seeded in DynamoDB
        return None

    def _hid(self, household_id: int | None) -> int:
        return self.household_id if household_id is None else int(household_id)

    @staticmethod
    def _pk(household_id: int) -> str:
        return f"H#{household_id}"

    def _query(self, pk: str, prefix: str) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Key

        items: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {"KeyConditionExpression": Key("pk").eq(pk) & Key("sk").begins_with(prefix)}
        while True:
            page = self.table.query(**kwargs)
            items.extend(page["Items"])
            if "LastEvaluatedKey" not in page:
                return items
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def _next(self, name: str) -> int:
        result = self.table.update_item(
            Key={"pk": "META", "sk": f"SEQ#{name}"},
            UpdateExpression="ADD n :one",
            ExpressionAttributeValues={":one": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(result["Attributes"]["n"])

    # -- people ----------------------------------------------------------------------------

    def add_person(self, name: str, household_id: int | None = None) -> dict[str, Any]:
        hid = self._hid(household_id)
        cleaned = " ".join(name.split())
        existing = self.find_person(cleaned, hid)
        if existing:
            return {"name": existing, "created": False}
        self.table.put_item(
            Item={
                "pk": self._pk(hid), "sk": f"P#{cleaned.lower()}", "name": cleaned,
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            },
            ConditionExpression="attribute_not_exists(pk)",
        )
        return {"name": cleaned, "created": True}

    def find_person(self, name: str, household_id: int | None = None) -> str | None:
        needle = " ".join(name.split()).lower()
        for known in self.list_people(household_id):
            if known.lower() == needle:
                return known
        return None

    def list_people(self, household_id: int | None = None) -> list[str]:
        hid = self._hid(household_id)
        names: dict[str, str] = {}
        for item in self._query(self._pk(hid), "P#"):
            names[item["name"].lower()] = item["name"]
        for item in self._query(self._pk(hid), "S#"):
            names.setdefault(item["person_name"].lower(), item["person_name"])
        return [names[key] for key in sorted(names)]

    def delete_person(self, name: str) -> bool:
        needle = " ".join(name.split()).lower()
        pk = self._pk(self.household_id)
        removed = False
        for item in self._query(pk, "S#"):
            if item["person_name"].lower() == needle:
                self._delete_schedule_rows(item)
                removed = True
        for item in self._query(pk, "P#"):
            if item["name"].lower() == needle:
                self.table.delete_item(Key={"pk": pk, "sk": item["sk"]})
                removed = True
        return removed

    # -- schedules -------------------------------------------------------------------------

    @staticmethod
    def _schedule(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(item["id"]),
            "household_id": int(item["household_id"]),
            "person_name": item["person_name"],
            "dose_label": item["dose_label"],
            "time_local": item["time_local"],
            "days": item.get("days", ALL_DAYS),
        }

    def list_schedules(self, household_id: int | None = None) -> list[dict[str, Any]]:
        rows = [self._schedule(item) for item in self._query(self._pk(self._hid(household_id)), "S#")]
        return sorted(rows, key=lambda r: (r["time_local"], r["person_name"], r["dose_label"], r["id"]))

    def add_schedule(
        self, person_name: str, dose_label: str, time_local: str, household_id: int | None = None, days: str = ALL_DAYS
    ) -> dict[str, Any]:
        hid = self._hid(household_id)
        self.add_person(person_name, hid)
        schedule_id = self._next("schedule")
        row = {
            "id": schedule_id, "household_id": hid, "person_name": person_name.strip(),
            "dose_label": dose_label.strip(), "time_local": time_local, "days": days,
        }
        self.table.put_item(Item={
            "pk": self._pk(hid), "sk": f"S#{schedule_id:012d}", **row,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        })
        return row

    def _find_schedule(self, schedule_id: int) -> dict[str, Any] | None:
        response = self.table.get_item(Key={"pk": self._pk(self.household_id), "sk": f"S#{int(schedule_id):012d}"})
        return response.get("Item")

    def update_schedule(self, schedule_id: int, dose_label: str, time_local: str, days: str) -> bool:
        if self._find_schedule(schedule_id) is None:
            return False
        self.table.update_item(
            Key={"pk": self._pk(self.household_id), "sk": f"S#{int(schedule_id):012d}"},
            UpdateExpression="SET dose_label = :l, time_local = :t, #d = :d",
            ExpressionAttributeNames={"#d": "days"},
            ExpressionAttributeValues={":l": dose_label.strip(), ":t": time_local, ":d": days},
        )
        return True

    def _delete_schedule_rows(self, item: dict[str, Any]) -> None:
        pk = self._pk(self.household_id)
        suffix = f"#{int(item['id']):012d}"
        for log in self._query(pk, "L#"):
            if log["sk"].endswith(suffix):
                self.table.delete_item(Key={"pk": pk, "sk": log["sk"]})
        self.table.delete_item(Key={"pk": pk, "sk": item["sk"]})

    def delete_schedule(self, schedule_id: int) -> bool:
        item = self._find_schedule(schedule_id)
        if item is None:
            return False
        self._delete_schedule_rows(item)
        return True

    # -- the log ---------------------------------------------------------------------------

    def get_log(self, schedule_id: int, day: str) -> dict[str, Any] | None:
        response = self.table.get_item(Key={"pk": self._pk(self.household_id), "sk": f"L#{day}#{int(schedule_id):012d}"})
        item = response.get("Item")
        if not item:
            return None
        return {k: item[k] for k in ("schedule_id", "day", "status", "reason", "logged_at")} | {
            "schedule_id": int(item["schedule_id"])
        }

    def upsert_log(self, schedule_id: int, day: str, status: str, reason: str, logged_at: str) -> None:
        if self._find_schedule(schedule_id) is None:
            return
        self.table.put_item(Item={
            "pk": self._pk(self.household_id), "sk": f"L#{day}#{int(schedule_id):012d}",
            "schedule_id": int(schedule_id), "day": day, "status": status, "reason": reason, "logged_at": logged_at,
        })

    def clear_logs(self, day: str | None = None, person_name: str = "") -> int:
        pk = self._pk(self.household_id)
        wanted: set[int] | None = None
        if person_name.strip():
            needle = " ".join(person_name.split()).lower()
            wanted = {int(r["id"]) for r in self._query(pk, "S#") if r["person_name"].lower() == needle}
        removed = 0
        for log in self._query(pk, "L#"):
            if day and log["day"] != day:
                continue
            if wanted is not None and int(log["schedule_id"]) not in wanted:
                continue
            self.table.delete_item(Key={"pk": pk, "sk": log["sk"]})
            removed += 1
        return removed

    # -- sign-in: who belongs to which household -------------------------------------------

    def account_for_sub(self, sub: str) -> dict[str, Any] | None:
        item = self.table.get_item(Key={"pk": f"SUB#{sub}", "sk": "ACCOUNT"}).get("Item")
        if not item:
            return None
        return {"email": item["email"], "household_id": int(item["household_id"]), "household_name": item["household_name"]}

    def ensure_account(self, sub: str, email: str, household_name: str) -> dict[str, Any]:
        """The first sign-in of a Cognito user creates their own empty household. Never takes one from a claim."""
        existing = self.account_for_sub(sub)
        if existing:
            return existing
        household_id = self._next("household")
        self.table.put_item(
            Item={"pk": f"SUB#{sub}", "sk": "ACCOUNT", "email": email, "household_id": household_id,
                  "household_name": household_name},
            ConditionExpression="attribute_not_exists(pk)",
        )
        return {"email": email, "household_id": household_id, "household_name": household_name}

    def save_session(self, token_hash: str, sub: str, expires: int) -> None:
        self.table.put_item(Item={"pk": f"SESSION#{token_hash}", "sk": "SESSION", "sub": sub, "ttl": int(expires)})

    def session_sub(self, token_hash: str) -> str | None:
        item = self.table.get_item(Key={"pk": f"SESSION#{token_hash}", "sk": "SESSION"}).get("Item")
        if not item or int(item["ttl"]) <= int(time.time()):  # TTL deletion can lag, so check the time too
            return None
        return str(item["sub"])

    def delete_session(self, token_hash: str) -> None:
        self.table.delete_item(Key={"pk": f"SESSION#{token_hash}", "sk": "SESSION"})
