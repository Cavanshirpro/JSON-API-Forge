#!/usr/bin/env python3
"""Exercise every copy-ready application in a fresh exampleApps checkout."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values
from fastapi.testclient import TestClient
from framework.factory import create_app
from generate_example_catalog import EXAMPLES
from jsonschema import Draft202012Validator


def _validate_editor_schemas() -> None:
    manifest = Draft202012Validator(
        json.loads(Path("schemas/manifest.schema.json").read_text(encoding="utf-8"))
    )
    fragment = Draft202012Validator(
        json.loads(Path("schemas/fragment.schema.json").read_text(encoding="utf-8"))
    )
    graph = Draft202012Validator(
        json.loads(Path("schemas/editor-graph.schema.json").read_text(encoding="utf-8"))
    )
    apps = sorted(path for path in Path("app").iterdir() if path.is_dir())
    if len(apps) != 25:
        raise RuntimeError(f"expected 25 copy-ready projects, found {len(apps)}")
    for app in apps:
        manifest.validate(json.loads((app / "app.json").read_text(encoding="utf-8")))
        for path in sorted((app / "config").glob("*.json")):
            fragment.validate(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((app / "graphs").glob("*.forgegraph.json")):
            graph.validate(json.loads(path.read_text(encoding="utf-8")))


def _admin(
    client: TestClient, values: Mapping[str, str | None], prefix: str, secret_name: str
) -> dict[str, str]:
    secret = values.get(secret_name)
    if not secret:
        raise RuntimeError(f"missing {secret_name}; run `forge init` first")
    response = client.post(
        f"{prefix}/admin/api-keys",
        headers={"X-API-Key": secret},
        json={"name": "example-ci-admin", "permissions": ["*"]},
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"cannot bootstrap {prefix}: HTTP {response.status_code} {response.text}"
        )
    return {"X-API-Key": response.json()["api_key"]}


def _exercise_generated_app(
    client: TestClient,
    values: Mapping[str, str | None],
    definition: Mapping[str, object],
) -> None:
    slug = str(definition["slug"])
    domain = str(definition["domain"])
    entity = str(definition["entity"])
    statuses = list(definition["statuses"])
    env = slug.upper().replace("-", "_")
    prefix = f"/api/{slug}/v1"
    auth = _admin(client, values, prefix, f"{env}_BOOTSTRAP_ADMIN_KEY")
    nonce = uuid.uuid4().hex[:12]
    payload: dict[str, object] = {
        "external_id": f"ci-{slug}-{nonce}",
        "name": f"CI {definition['name']} record",
        "status": statuses[0],
        "owner_id": "ci-operator",
        "amount": 1250,
        "priority": 7,
        "metadata": {"source": "example-smoke", "nonce": nonce},
    }
    if definition.get("plugin_catalog"):
        payload.update(
            {
                "plugin_id": "example.analytics",
                "version": "1.0.0",
                "publisher": "Example Publisher",
                "platform": "any",
                "download_url": "https://packages.example.invalid/example-analytics.zip",
                "sha256": "a" * 64,
                "permissions": ["graph.nodes.register"],
                "description": "Synthetic catalog record used by the example smoke test.",
            }
        )
    route = f"{prefix}/{domain}/{entity}"
    created = client.post(route, headers=auth, json=payload)
    assert created.status_code == 200, (
        f"{slug} create: {created.status_code} {created.text}"
    )
    item_id = created.json()["id"]
    listed = client.get(f"{route}?status={statuses[0]}&sort=-priority", headers=auth)
    assert listed.status_code == 200 and any(
        item["id"] == item_id for item in listed.json()["items"]
    ), listed.text

    dashboard = client.get(f"{prefix}/rpc/{domain}.dashboard", headers=auth)
    assert dashboard.status_code == 200 and "status_summary" in dashboard.json(), (
        dashboard.text
    )
    transition_headers = {**auth, "Idempotency-Key": f"transition-{slug}-{nonce}"}
    transition_body = {
        "record_id": item_id,
        "next_status": statuses[1],
        "actor_id": "ci-operator",
        "reason": "example lifecycle smoke",
    }
    transitioned = client.post(
        f"{prefix}/rpc/{domain}.transition",
        headers=transition_headers,
        json=transition_body,
    )
    assert transitioned.status_code == 200, (
        f"{slug} transition: {transitioned.status_code} {transitioned.text}"
    )
    if slug == "commerce-core":
        replay = client.post(
            f"{prefix}/rpc/{domain}.transition",
            headers=transition_headers,
            json=transition_body,
        )
        assert (
            replay.status_code == 200 and replay.json()["_idempotent_replay"] is True
        ), replay.text
    event = client.post(
        f"{prefix}/events/{slug}-updates",
        headers=auth,
        json={"record_id": item_id, "status": statuses[1], "source": "smoke"},
    )
    assert event.status_code == 200 and event.json()["published"] is True, event.text


def main() -> None:
    logging.disable(logging.CRITICAL)
    _validate_editor_schemas()
    values = dotenv_values(".env")
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        catalog = client.get("/api/public-catalog/v1/content/catalog")
        assert catalog.status_code == 200 and len(catalog.json()) >= 3
        assert client.get("/api/task-board/v1/tasks").status_code == 401

        task_auth = _admin(
            client, values, "/api/task-board/v1", "TASK_BOARD_BOOTSTRAP_ADMIN_KEY"
        )
        task = client.post(
            "/api/task-board/v1/tasks",
            headers=task_auth,
            json={"title": "Ship hardened branch", "status": "doing", "priority": 5},
        )
        assert task.status_code == 200, task.text
        tasks = client.get(
            "/api/task-board/v1/tasks?status=doing&sort=-priority", headers=task_auth
        )
        assert (
            tasks.status_code == 200
            and tasks.json()["items"][0]["title"] == "Ship hardened branch"
        )

        guild_auth = _admin(
            client, values, "/api/guild-ledger/v1", "GUILD_LEDGER_BOOTSTRAP_ADMIN_KEY"
        )
        for member, display_name in (("ci-member-a", "Ada"), ("ci-member-b", "Linus")):
            account = client.post(
                "/api/guild-ledger/v1/ledger/accounts",
                headers=guild_auth,
                json={"member_id": member, "display_name": display_name},
            )
            assert account.status_code == 200, account.text
        grant = client.post(
            "/api/guild-ledger/v1/rpc/ledger.grant",
            headers={**guild_auth, "Idempotency-Key": "ci-grant-1"},
            json={"member_id": "ci-member-a", "amount": 100, "reason": "seed"},
        )
        assert grant.status_code == 200, grant.text
        transfer_headers = {**guild_auth, "Idempotency-Key": "ci-transfer-1"}
        transfer_body = {
            "from_member": "ci-member-a",
            "to_member": "ci-member-b",
            "amount": 25,
            "reason": "reward",
        }
        transfer = client.post(
            "/api/guild-ledger/v1/rpc/ledger.transfer",
            headers=transfer_headers,
            json=transfer_body,
        )
        replay = client.post(
            "/api/guild-ledger/v1/rpc/ledger.transfer",
            headers=transfer_headers,
            json=transfer_body,
        )
        assert transfer.status_code == 200, transfer.text
        assert (
            replay.status_code == 200 and replay.json()["_idempotent_replay"] is True
        ), replay.text

        realtime_auth = _admin(
            client,
            values,
            "/api/realtime-support/v1",
            "REALTIME_SUPPORT_BOOTSTRAP_ADMIN_KEY",
        )
        event = client.post(
            "/api/realtime-support/v1/events/ticket-updates",
            headers=realtime_auth,
            json={"ticket_id": 1, "status": "open"},
        )
        assert event.status_code == 200 and event.json()["published"] is True, (
            event.text
        )

        media_auth = _admin(
            client, values, "/api/media-library/v1", "MEDIA_LIBRARY_BOOTSTRAP_ADMIN_KEY"
        )
        uploaded = client.post(
            "/api/media-library/v1/media",
            headers=media_auth,
            files={"file": ("ci-smoke.png", b"\x89PNG\r\n\x1a\nforge", "image/png")},
        )
        assert uploaded.status_code == 200, uploaded.text
        media_id = uploaded.json()["id"]
        fetched = client.get(
            f"/api/media-library/v1/media/{media_id}", headers=media_auth
        )
        assert fetched.status_code == 200 and fetched.content.startswith(b"\x89PNG"), (
            fetched.text
        )
        deleted = client.delete(
            f"/api/media-library/v1/media/{media_id}", headers=media_auth
        )
        assert deleted.status_code == 200 and deleted.json()["deleted"] is True, (
            deleted.text
        )

        for definition in EXAMPLES:
            _exercise_generated_app(client, values, definition)

    print(
        "OK: 25 example applications passed schema, CRUD, RPC, idempotency, realtime, media and public-data smoke tests"
    )


if __name__ == "__main__":
    main()
