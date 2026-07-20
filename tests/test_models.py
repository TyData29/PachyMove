from __future__ import annotations

import json

from pgaudit_runner.models import (
    ConnectionInfo,
    ErrorDetail,
    QueryResult,
    QuerySpec,
    RunMetadata,
    RunSummary,
    SelectionInfo,
    to_json_dict,
)


def test_query_spec_default_lists_are_not_shared_between_instances():
    a = QuerySpec(id="a", title="A", file="a.sql", scope="instance")
    b = QuerySpec(id="b", title="B", file="b.sql", scope="instance")
    a.tags.append("x")
    assert b.tags == []


def test_query_result_minimal_fields_only():
    r = QueryResult(
        id="a", title="A", scope="instance", target="instance",
        sql="SELECT 1", status="success",
    )
    assert r.error is None
    assert r.rows is None
    assert r.skip_reason is None


def test_to_json_dict_is_json_serializable_with_error_and_none_fields():
    metadata = RunMetadata(
        tool_version="1.0.0",
        manifest_name="test",
        started_at="2026-01-01T00:00:00+00:00",
        finished_at=None,
        source=ConnectionInfo(host="h", port=5432, user="u"),
        selection=SelectionInfo(dry_run=True),
        summary=RunSummary(total=1, error=1),
    )
    results = [
        QueryResult(
            id="a", title="A", scope="instance", target="instance",
            sql="DROP TABLE x", status="error",
            error=ErrorDetail(message="rejetée", full_traceback="", sqlstate=None),
        )
    ]

    payload = to_json_dict(metadata, results)
    decoded = json.loads(json.dumps(payload, ensure_ascii=False))

    assert decoded["metadata"]["finished_at"] is None
    assert decoded["metadata"]["source"]["host"] == "h"
    assert decoded["metadata"]["target"] is None
    assert decoded["metadata"]["same_server"] is None
    assert decoded["results"][0]["status"] == "error"
    assert decoded["results"][0]["error"]["message"] == "rejetée"
    assert decoded["results"][0]["side"] == "source"
    assert decoded["results"][0]["applies_to"] == []
