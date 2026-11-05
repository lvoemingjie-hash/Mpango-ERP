"""A1 file contracts, including controls callable unchanged against E51.

These tests do not establish shutdown, crash recovery or writer fencing.
"""
import asyncio
import builtins
import codecs
import csv
import hashlib
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest


class Rows:
    def __init__(self, rows):
        self.rows = list(rows)

    def fetchmany(self, size):
        batch, self.rows = self.rows[:size], self.rows[size:]
        return batch


def payload(fmt="csv"):
    return {
        "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
        "tenant_schema": "t_550e8400e29b41d4a716446655440000",
        "user_id": "770e8400-e29b-41d4-a716-446655440000",
        "view": "sales_daily", "metrics": ["revenue"], "dimensions": ["date"],
        "format": fmt, "file_id": uuid.uuid4().hex, "limit": 100,
    }


def metadata(path, identity):
    return {
        "metadata_version": 1, "file_id": identity["file_id"],
        "file_path": str(path), "file_name": path.name,
        "row_count": 1, "file_size_bytes": path.stat().st_size,
        "content_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "format": identity["format"], "tenant_id": identity["tenant_id"],
        "user_id": identity["user_id"],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


@pytest.mark.asyncio
async def test_csv_formula_prefixes_and_delimiters(tmp_path):
    from jobs.export_jobs import _write_csv_streaming

    dangerous = ["=1+1", "+1", "-2", "@SUM(1,1)", "＝1", "＋2", "－3", "＠A1",
                 " \ufeff\x01＝1", "\tplain", "\rplain", "\nplain", "\u2003＋1"]
    ordinary = ["00123", "12345678901234567890", 'Acme, "A"; B\nC', "plain\ufefftext"]
    out = tmp_path / "formula.csv"
    await _write_csv_streaming(Rows([(v,) for v in dangerous + ordinary]), ["＝header"], out)
    parsed = list(csv.reader(io.StringIO(out.read_bytes().decode("utf-8-sig"), newline="")))
    assert parsed[0] == ["'＝header"], "DANGEROUS_HEADER_ACCEPTED"
    assert [r[0] for r in parsed[1:len(dangerous) + 1]] == ["'" + v for v in dangerous], "DANGEROUS_TEXT_ACCEPTED"
    assert [r[0] for r in parsed[len(dangerous) + 1:]] == ordinary


@pytest.mark.asyncio
async def test_csv_utf8_bom_and_typed_precision(tmp_path):
    from jobs.export_jobs import _write_csv_streaming

    identifier = uuid.UUID("770e8400-e29b-41d4-a716-446655440000")
    row = (Decimal("1234567890123456.1234"), Decimal("-0.0100"), identifier,
           "000123", "123456789012345678901", "cell\ufeffdata", 42)
    out = tmp_path / "exact.csv"
    assert await _write_csv_streaming(Rows([row]), ["价", "negative", "uuid", "id", "long", "text", "count"], out) == 1
    raw = out.read_bytes()
    assert raw.startswith(codecs.BOM_UTF8) and not raw.startswith(codecs.BOM_UTF8 * 2)
    assert raw.count(codecs.BOM_UTF8) == 2, "cell BOM is data, not a second encoding prefix"
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    assert rows[1] == ["1234567890123456.1234", "-0.0100", str(identifier), "000123",
                       "123456789012345678901", "cell\ufeffdata", "42"]


@pytest.mark.asyncio
async def test_xlsx_literal_text_and_exact_decimal(tmp_path):
    from jobs.export_jobs import _write_xlsx_streaming
    from openpyxl import load_workbook

    identifier = uuid.UUID("770e8400-e29b-41d4-a716-446655440000")
    row = (Decimal("1234567890123456.1234"), Decimal("-0.0100"), identifier,
           "000123", "123456789012345678901", "=1+1", "\t＠A1", 42)
    out = tmp_path / "literal.xlsx"
    await _write_xlsx_streaming(Rows([row]), ["=header"] + ["text"] * 6 + ["count"], out)
    book = load_workbook(out, read_only=True, data_only=False, keep_links=False)
    try:
        rows = list(book.active.rows)
        assert rows[0][0].value == "=header" and rows[0][0].data_type == "s"
        assert [c.value for c in rows[1]] == ["1234567890123456.1234", "-0.0100", str(identifier),
                                            "000123", "123456789012345678901", "=1+1", "\t＠A1", 42]
        assert all(c.data_type == "s" for c in rows[1][:-1])
        assert rows[1][-1].data_type == "n"
    finally:
        book.close()


@pytest.mark.asyncio
async def test_xlsx_is_real_ooxml_not_csv(tmp_path):
    from jobs.export_jobs import _write_xlsx_streaming, validate_export_file
    from xml.etree import ElementTree as ET

    out = tmp_path / "real.xlsx"
    await _write_xlsx_streaming(Rows([("=1+1",)]), ["header"], out)
    assert zipfile.is_zipfile(out)
    with zipfile.ZipFile(out) as archive:
        names = archive.namelist()
        assert {"[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml"}.issubset(names)
        assert not any("vba" in n.lower() or "externallinks" in n.lower() for n in names)
        worksheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        assert not worksheet.findall(".//{*}f")
    validate_export_file(out, "xlsx")
    fake = tmp_path / "not-xlsx.xlsx"
    fake.write_bytes(codecs.BOM_UTF8 + b"header\r\nvalue\r\n")
    with pytest.raises(ValueError, match="EXPORT_FILE_FORMAT_INVALID"):
        validate_export_file(fake, "xlsx")
    with zipfile.ZipFile(fake, "w") as archive:
        for name in ("[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml"):
            archive.writestr(name, "<fake/>")
    with pytest.raises(ValueError, match="EXPORT_XLSX_FORMAT_INVALID"):
        validate_export_file(fake, "xlsx")


@pytest.mark.asyncio
async def test_missing_openpyxl_refuses_api_and_worker(tmp_path, monkeypatch):
    # No imports of candidate-only helpers: this same control must reach E51's writer.
    from jobs import export_jobs
    from api.schemas.jobs import ExportRequest
    from api.v1.exports import create_export
    from tests.test_dc10e_export_worker_tenant_context import _request_with_context, _exports_create_token

    original_import = builtins.__import__
    def without_xlsx(name, *args, **kwargs):
        if name == "openpyxl" or name.startswith("openpyxl."):
            raise ImportError("synthetic dependency absence")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", without_xlsx)
    monkeypatch.setattr(export_jobs, "EXPORT_DIR", tmp_path)
    out = tmp_path / "missing.xlsx"
    error = None
    try:
        await export_jobs._write_xlsx_streaming(Rows([("value",)]), ["header"], out)
    except ValueError as caught:
        error = str(caught)
    assert error == "EXPORT_XLSX_DEPENDENCY_UNAVAILABLE", "MISSING_XLSX_DEPENDENCY_ACCEPTED_OR_FAKE_XLSX_PUBLISHED"
    assert not out.exists() and not list(tmp_path.iterdir())
    with pytest.raises(ValueError, match="EXPORT_XLSX_DEPENDENCY_UNAVAILABLE"):
        await export_jobs.export_report_worker(payload("xlsx"))
    class NoEnqueue:
        calls = 0
        async def enqueue(self, **kwargs):
            self.calls += 1
            raise AssertionError("XLSX_DEPENDENCY_REFUSAL_MUST_PRECEDE_PERSISTENCE")
    queue = NoEnqueue()
    monkeypatch.setattr("main.get_job_queue", lambda: queue)
    request = _request_with_context()
    token = await _exports_create_token(request)
    response = await create_export(request, ExportRequest(view="sales_daily", metrics=["revenue"], format="xlsx"), token)
    assert response.status_code == 503
    assert json.loads(response.body)["error"]["code"] == "EXPORT_XLSX_DEPENDENCY_UNAVAILABLE"
    assert queue.calls == 0 and not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_controlled_cancel_or_error_never_publishes_partial_file(tmp_path):
    from jobs.export_jobs import _write_csv_streaming, _write_xlsx_streaming

    for suffix, writer in [("csv", _write_csv_streaming), ("xlsx", _write_xlsx_streaming)]:
        for error in (asyncio.CancelledError, RuntimeError):
            out = tmp_path / (error.__name__ + "." + suffix)
            out.write_bytes(b"previous-complete-file")
            foreign = tmp_path / (out.name + ".part.other-task")
            foreign.write_bytes(b"not-ours")
            class Interrupted:
                calls = 0
                def fetchmany(self, size):
                    self.calls += 1
                    if self.calls == 1:
                        return [("first",)]
                    raise error("controlled write boundary")
            with pytest.raises(error):
                await writer(Interrupted(), ["header"], out)
            assert out.read_bytes() == b"previous-complete-file"
            assert foreign.read_bytes() == b"not-ours"
            assert list(tmp_path.glob(out.name + ".part.*")) == [foreign]
            assert not list(tmp_path.glob("*.meta.json"))


@pytest.mark.asyncio
async def test_download_rejects_mislabeled_or_mismatched_artifacts(tmp_path, monkeypatch):
    from api.v1.exports import download_export, _find_job_metadata
    from jobs import export_jobs
    from tests.test_dc10e_export_worker_tenant_context import _request_with_context, _exports_create_token
    from tests.test_s6_4_async_exports import _FakeSession

    monkeypatch.setattr(export_jobs, "EXPORT_DIR", tmp_path)
    identity = payload()
    path = tmp_path / (identity["file_id"] + ".csv")
    await export_jobs._write_csv_streaming(Rows([("good",)]), ["header"], path)
    good = metadata(path, identity)
    export_jobs._write_metadata(identity["file_id"], good)
    job = SimpleNamespace(status="completed", payload=identity)
    monkeypatch.setattr("database.session.AsyncSessionLocal", lambda: _FakeSession(job))
    request = _request_with_context()
    token = await _exports_create_token(request)
    job_id = str(uuid.uuid4())
    assert (await download_export(request, job_id, token)).status_code == 200
    other_request = _request_with_context("660e8400-e29b-41d4-a716-446655440000")
    other_token = await _exports_create_token(other_request)
    response = await download_export(other_request, job_id, other_token)
    assert response.status_code == 404 and json.loads(response.body)["error"]["code"] == "EXPORT_NOT_FOUND"
    assert _find_job_metadata(job_id, {**identity, "file_id": "missing-same-tenant-file"}) is None
    for key, value, status in [("file_id", "other-file", 404), ("tenant_id", "other-tenant", 404),
                               ("user_id", "other-user", 409), ("content_sha256", "0" * 64, 409),
                               ("file_size_bytes", path.stat().st_size + 1, 409), ("format", "xlsx", 409)]:
        export_jobs._write_metadata(identity["file_id"], {**good, key: value})
        response = await download_export(request, job_id, token)
        assert response.status_code == status
        assert json.loads(response.body)["error"]["code"] == (
            "EXPORT_FILE_MISSING" if status == 404 else "EXPORT_FILE_INVALID")
        assert _find_job_metadata(job_id, identity) is None
    export_jobs._write_metadata(identity["file_id"], good)
    moved = tmp_path / "other-real.csv"
    moved.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(moved)
    assert (await download_export(request, job_id, token)).status_code == 404
    path.unlink()
    identity["format"] = "xlsx"
    path = tmp_path / (identity["file_id"] + ".xlsx")
    path.write_bytes(codecs.BOM_UTF8 + b"header\r\nnot-an-xlsx\r\n")
    before = path.read_bytes()
    export_jobs._write_metadata(identity["file_id"], metadata(path, identity))
    response = await download_export(request, job_id, token)
    assert response.status_code == 409
    assert json.loads(response.body)["error"]["code"] == "EXPORT_FILE_INVALID"
    assert "new export" in json.loads(response.body)["error"]["message"]
    assert path.read_bytes() == before


@pytest.mark.asyncio
async def test_invalid_format_and_nonfinite_values_fail_closed(tmp_path, monkeypatch):
    from jobs import export_jobs

    monkeypatch.setattr(export_jobs, "EXPORT_DIR", tmp_path)
    with pytest.raises(ValueError, match="EXPORT_FORMAT_INVALID"):
        await export_jobs.export_report_worker(payload("xls"))
    for fmt, writer in [("csv", export_jobs._write_csv_streaming), ("xlsx", export_jobs._write_xlsx_streaming)]:
        for i, value in enumerate([Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), float("nan"), float("inf")]):
            out = tmp_path / (str(i) + "." + fmt)
            with pytest.raises(ValueError, match="EXPORT_NONFINITE_VALUE"):
                await writer(Rows([(value,)]), ["header"], out)
            assert not out.exists() and not list(tmp_path.glob(out.name + ".part.*"))
    for value in ["bad\x00text", "bad\x0btext", "bad\ufffetext", "x" * 32768]:
        out = tmp_path / "invalid-text.xlsx"
        with pytest.raises(ValueError, match="EXPORT_XLSX_TEXT_INVALID"):
            await export_jobs._write_xlsx_streaming(Rows([(value,)]), ["header"], out)
        assert not out.exists() and not list(tmp_path.glob(out.name + ".part.*"))
