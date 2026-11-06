"""Offline tests: Drive is mocked and all filesystem writes use tmp_path."""
import importlib
import json
import sys
from datetime import datetime
from unittest.mock import MagicMock, call

import pytest


@pytest.fixture
def app(monkeypatch, tmp_path):
    # Patch before importing: event_downloader builds its Drive client at import time.
    import googleapiclient.discovery

    monkeypatch.setenv("GOOGLE_DRIVE_API_KEY", "test-api-key")
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "test-folder-id")
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setattr(googleapiclient.discovery, "build", MagicMock())
    monkeypatch.delitem(sys.modules, "event_downloader", raising=False)
    module = importlib.import_module("event_downloader")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "event_img").mkdir()

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 4, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(module, "datetime", FrozenDatetime)
    yield module
    sys.modules.pop("event_downloader", None)


def event(file_id="new", date="11.05.26", band="Band"):
    return {"id": file_id, "date": date, "bandnames": band,
            "filename": f"{date} {band}.jpg", "extension": "jpg"}


def remote(item):
    return {"id": item["id"], "name": item["filename"], "mimeType": "image/jpeg"}


def test_list_files_paginates(app):
    api = app.service.files.return_value
    api.list.return_value.execute.side_effect = [
        {"files": [{"id": "a"}], "nextPageToken": "page-2"},
        {"files": [{"id": "b"}]},
    ]
    assert app.ListFilesInPublicFolder("folder") == [{"id": "a"}, {"id": "b"}]
    assert api.list.call_args_list == [
        call(q="'folder' in parents and trashed = false",
             fields="nextPageToken, files(id, name, mimeType)", pageToken=token)
        for token in (None, "page-2")
    ]


@pytest.mark.parametrize("response", [{}, {"files": []}, {"nextPageToken": ""}])
def test_list_files_empty(app, response):
    app.service.files.return_value.list.return_value.execute.return_value = response
    assert app.ListFilesInPublicFolder("folder") == []


def test_list_files_propagates_api_error(app):
    app.service.files.return_value.list.return_value.execute.side_effect = RuntimeError("offline")
    with pytest.raises(RuntimeError, match="offline"):
        app.ListFilesInPublicFolder("folder")


def test_download_writes_all_chunks_and_closes_file(app, monkeypatch, capsys):
    handles = []

    class Downloader:
        def __init__(self, handle, request):
            handles.append(handle)
            assert request is app.service.files.return_value.get_media.return_value
            self.handle = handle
            self.chunk = 0

        def next_chunk(self):
            self.chunk += 1
            assert self.handle.name.endswith("poster.jpg.tmp")
            assert not (app.Path.cwd() / "event_img/poster.jpg").exists()
            self.handle.write(b"abc")
            status = MagicMock()
            status.progress.return_value = self.chunk / 2
            return status, self.chunk == 2

    monkeypatch.setattr(app, "MediaIoBaseDownload", Downloader)
    assert app.DownloadFile("file-id", "poster.jpg") == "poster.jpg"
    assert not (app.Path.cwd() / "event_img/poster.jpg.tmp").exists()
    assert (app.Path.cwd() / "event_img/poster.jpg").read_bytes() == b"abcabc"
    assert handles[0].closed
    app.service.files.return_value.get_media.assert_called_once_with(fileId="file-id")
    assert capsys.readouterr().out == "Progress: 50%\nProgress: 100%\n"


def test_download_returns_none_on_failure_and_closes_file(app, monkeypatch):
    factory = MagicMock()
    factory.return_value.next_chunk.side_effect = RuntimeError("download failed")
    monkeypatch.setattr(app, "MediaIoBaseDownload", factory)
    assert app.DownloadFile("id", "poster.jpg") is None
    assert not (app.Path.cwd() / "event_img/poster.jpg").exists()
    assert factory.call_args.args[0].closed


def test_build_events_path(app):
    assert app.BuildEventsFilePath() == app.Path.cwd() / "event_img/events.json"


@pytest.mark.parametrize("data", [[], [event()], [event(band="Bänd 音楽")]])
def test_json_round_trip(app, data):
    app.WriteCurrentEvents(data)
    assert json.loads(app.BuildEventsFilePath().read_text()) == data
    assert app.ReadCurrentEvents() == data


@pytest.mark.parametrize("content", [None, "", "{broken json"])
def test_read_missing_or_invalid_json(app, content, caplog):
    if content is not None:
        app.BuildEventsFilePath().write_text(content)
    assert app.ReadCurrentEvents() is None
    assert "Error reading current events file" in caplog.text


def test_write_failure_is_logged(app, monkeypatch, caplog):
    monkeypatch.setattr(app, "BuildEventsFilePath", lambda: app.Path("missing/events.json"))
    app.WriteCurrentEvents([event()])
    assert "Error writing file" in caplog.text


@pytest.mark.parametrize("exists", [True, False])
def test_remove_image_handles_existing_and_missing_files(app, exists):
    image = app.Path.cwd() / "event_img/poster.jpg"
    other = image.with_name("keep.jpg")
    other.write_bytes(b"keep")
    if exists:
        image.write_bytes(b"delete")
    app.RemoveEventImage(image.name)
    assert not image.exists()
    assert other.read_bytes() == b"keep"


@pytest.mark.parametrize("date,expired", [
    ("11.01.26", True), ("11.02.26", False),
    ("11.03.26", False), ("11.04.26", False), ("12.01.26", False),
])
def test_purge_cutoff_at_noon(app, date, expired):
    item = event(date=date)
    image = app.Path.cwd() / "event_img" / item["filename"]
    image.write_bytes(b"poster")
    original = [item]
    assert app.PurgeExpiredEvents(original) == ([] if expired else [item])
    assert image.exists() is not expired
    assert original == [item]


def test_purge_one_microsecond_after_cutoff(app, monkeypatch):
    class AfterNoon(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 11, 4, 12, 0, 0, 1)

    monkeypatch.setattr(app, "datetime", AfterNoon)
    assert app.PurgeExpiredEvents([event(date="11.02.26")]) == []


def test_purge_empty(app):
    assert app.PurgeExpiredEvents([]) == []


def test_purge_preserves_order_and_tolerates_missing_images(app):
    first, last = event("a"), event("b", "12.01.26")
    assert app.PurgeExpiredEvents([first, event("old", "10.01.26"), last]) == [first, last]


@pytest.mark.parametrize("date", ["bad", "02.30.26"])
def test_purge_invalid_date_raises(app, date):
    with pytest.raises(ValueError):
        app.PurgeExpiredEvents([event(date=date)])


@pytest.mark.parametrize("existing,new,expected", [
    ([], [], ([], [])), ([], [event()], ([event()], [])),
    ([event()], [], ([], [])),
    ([event()], [event()], ([], [])),
    ([event()], [event(band="Renamed")], ([], [])),
    ([event()], [event("b")], ([], [event("b")])),
    ([event()], [event("b", band="Other"), event(), event("a")],
     ([event("b", band="Other")], [event("a")])),
])
def test_compare_by_drive_id_and_filename(app, existing, new, expected):
    before_existing, before_new = list(existing), list(new)
    assert app.MapAndCompareEvents(existing, new) == expected
    assert existing == before_existing
    assert new == before_new


@pytest.mark.parametrize("success", [True, False])
def test_main_replaces_existing_file_and_retries_failed_update(app, monkeypatch, success):
    old, replacement = event("old"), event("replacement")
    added = event("added", band="Other")
    app.WriteCurrentEvents([old])
    monkeypatch.setattr(app, "ListFilesInPublicFolder", lambda _: [
        remote(replacement), remote(added)
    ])
    download = MagicMock(side_effect=[
        replacement["filename"] if success else None, added["filename"]
    ])
    monkeypatch.setattr(app, "DownloadFile", download)

    app.main()
    assert app.ReadCurrentEvents() == [replacement if success else old, added]
    assert download.call_args_list == [
        call(replacement["id"], replacement["filename"]),
        call(added["id"], added["filename"]),
    ]

    download.reset_mock(side_effect=True)
    download.return_value = replacement["filename"]
    app.main()
    assert app.ReadCurrentEvents() == [replacement, added]
    if success:
        download.assert_not_called()
    else:
        download.assert_called_once_with(replacement["id"], replacement["filename"])


def test_main_sync_downloads_only_new_files_and_sorts(app, monkeypatch):
    existing = event("existing", "12.01.26")
    added = event("added", "11.06.26")
    expired = event("expired", "10.01.26")
    app.WriteCurrentEvents([existing, expired])
    old_image = app.Path.cwd() / "event_img" / expired["filename"]
    old_image.write_bytes(b"old")
    listing = MagicMock(return_value=[remote(existing), remote(added), {"id": "txt", "name": "notes.txt"}])
    download = MagicMock(return_value="downloaded.jpg")
    monkeypatch.setattr(app, "ListFilesInPublicFolder", listing)
    monkeypatch.setattr(app, "DownloadFile", download)
    app.main()
    listing.assert_called_once_with(app.FOLDER_ID)
    download.assert_called_once_with(added["id"], added["filename"])
    assert app.ReadCurrentEvents() == [added, existing]
    assert not old_image.exists()
    app.main()
    assert download.call_count == 1  # A second run is idempotent.


@pytest.mark.parametrize("initial", [None, [], "invalid"])
def test_main_initializes_missing_empty_or_invalid_json(app, monkeypatch, initial):
    if initial == "invalid":
        app.BuildEventsFilePath().write_text("bad json")
    elif initial is not None:
        app.WriteCurrentEvents(initial)
    item = event()
    monkeypatch.setattr(app, "ListFilesInPublicFolder", lambda _: [remote(item)])
    download = MagicMock(return_value="downloaded.jpg")
    monkeypatch.setattr(app, "DownloadFile", download)
    app.main()
    assert app.ReadCurrentEvents() == [item]
    download.assert_called_once_with(item["id"], item["filename"])


@pytest.mark.parametrize("failure", [False, True])
def test_main_handles_empty_listing_or_api_failure(app, monkeypatch, caplog, failure):
    listing = MagicMock(return_value=[])
    if failure:
        listing.side_effect = RuntimeError("offline")
    monkeypatch.setattr(app, "ListFilesInPublicFolder", listing)
    write, download = MagicMock(return_value="downloaded.jpg"), MagicMock()
    monkeypatch.setattr(app, "WriteCurrentEvents", write)
    monkeypatch.setattr(app, "DownloadFile", download)
    app.main()
    download.assert_not_called()
    if failure:
        write.assert_not_called()
        assert "offline" in caplog.text
    else:
        write.assert_called_once_with([])


def test_main_download_failure_does_not_save_failed_event(app, monkeypatch):
    app.WriteCurrentEvents([])
    monkeypatch.setattr(app, "ListFilesInPublicFolder", lambda _: [remote(event())])
    monkeypatch.setattr(app, "DownloadFile", MagicMock(return_value=None))
    app.main()
    assert app.ReadCurrentEvents() == []


def test_regression_empty_drive_persists_purge(app, monkeypatch):
    app.WriteCurrentEvents([event(date="10.01.26")])
    monkeypatch.setattr(app, "ListFilesInPublicFolder", lambda _: [])
    app.main()
    assert app.ReadCurrentEvents() == []


@pytest.mark.parametrize("already_present", [True, False])
def test_main_downloads_expired_files_still_present_on_authoritative_drive(app, monkeypatch, already_present):
    old = event(date="10.01.26")
    app.WriteCurrentEvents([old] if already_present else [])
    monkeypatch.setattr(app, "ListFilesInPublicFolder", lambda _: [remote(old)])
    download = MagicMock(return_value="downloaded.jpg")
    monkeypatch.setattr(app, "DownloadFile", download)
    app.main()
    download.assert_called_once_with(old["id"], old["filename"])
    assert app.ReadCurrentEvents() == [old]


@pytest.mark.parametrize("status_code", [403, 404, 429, 500, 503])
def test_real_downloader_http_error_exits_without_retry(app, status_code, caplog):
    """Exercise the real downloader with a fake HTTP transport."""
    import httplib2
    from googleapiclient.http import HttpRequest

    transport = MagicMock()
    transport.request.return_value = (
        httplib2.Response({"status": str(status_code)}), b"download failed"
    )
    request = HttpRequest(transport, lambda *_: None, "https://example.test/poster")
    app.service.files.return_value.get_media.return_value = request

    assert app.DownloadFile("id", "poster.jpg") is None
    assert str(status_code) in caplog.text
    assert transport.request.call_count == 1
    assert not (app.Path.cwd() / "event_img/poster.jpg").exists()
    assert (app.Path.cwd() / "event_img/poster.jpg.tmp").read_bytes() == b""


def test_real_downloader_timeout_after_partial_data(app):
    import httplib2
    from googleapiclient.http import HttpRequest

    transport = MagicMock()
    transport.request.side_effect = [
        (httplib2.Response({"status": "206", "content-range": "bytes 0-2/6"}), b"abc"),
        TimeoutError("connection timed out"),
    ]
    app.service.files.return_value.get_media.return_value = HttpRequest(
        transport, lambda *_: None, "https://example.test/poster"
    )

    assert app.DownloadFile("id", "poster.jpg") is None

    assert transport.request.call_count == 2
    assert not (app.Path.cwd() / "event_img/poster.jpg").exists()
    assert (app.Path.cwd() / "event_img/poster.jpg.tmp").read_bytes() == b"abc"


def test_real_downloader_repeats_request_when_server_makes_no_progress(app):
    """Bound the simulation with an exception so this test cannot hang."""
    import httplib2
    from googleapiclient.http import HttpRequest

    transport = MagicMock()
    empty_chunk = (
        httplib2.Response({"status": "206", "content-range": "bytes 0-0/6"}), b""
    )
    transport.request.side_effect = [empty_chunk, empty_chunk, TimeoutError("stop simulation")]
    app.service.files.return_value.get_media.return_value = HttpRequest(
        transport, lambda *_: None, "https://example.test/poster"
    )

    assert app.DownloadFile("id", "poster.jpg") is None

    assert transport.request.call_count == 3
    ranges = [entry.kwargs["headers"]["range"] for entry in transport.request.call_args_list]
    assert len(set(ranges)) == 1


def test_download_request_setup_failure_returns_none(app, caplog):
    app.service.files.return_value.get_media.side_effect = RuntimeError("request failed")
    assert app.DownloadFile("id", "poster.jpg") is None
    assert "request failed" in caplog.text
    assert list((app.Path.cwd() / "event_img").iterdir()) == []


@pytest.mark.parametrize("fail_at", ["chunk", "rename", None])
def test_download_preserves_existing_image_until_success(app, monkeypatch, fail_at, caplog):
    target = app.Path.cwd() / "event_img/poster.jpg"
    temporary = target.with_name(target.name + ".tmp")
    target.write_bytes(b"original")
    temporary.write_bytes(b"stale incomplete download")

    class Downloader:
        def __init__(self, handle, request):
            self.handle = handle

        def next_chunk(self):
            assert target.read_bytes() == b"original"
            self.handle.write(b"new")
            if fail_at == "chunk":
                raise RuntimeError("chunk failed")
            status = MagicMock()
            status.progress.return_value = 1
            return status, True

    monkeypatch.setattr(app, "MediaIoBaseDownload", Downloader)
    if fail_at == "rename":
        def fail_replace(source, destination):
            assert source == temporary
            assert destination == target
            assert temporary.read_bytes() == b"new"
            raise PermissionError("rename failed")

        monkeypatch.setattr(app.Path, "replace", fail_replace)

    result = app.DownloadFile("id", "poster.jpg")
    if fail_at:
        assert result is None
        assert target.read_bytes() == b"original"
        assert temporary.read_bytes() == b"new"
        assert "File download failed" in caplog.text
    else:
        assert result == "poster.jpg"
        assert target.read_bytes() == b"new"
        assert not temporary.exists()


def test_download_file_open_failure_returns_none(app, monkeypatch, caplog):
    monkeypatch.setattr(app.io, "FileIO", MagicMock(side_effect=PermissionError("cannot write")))
    assert app.DownloadFile("id", "poster.jpg") is None
    assert "cannot write" in caplog.text


def test_main_continues_after_failed_download_and_retries_next_run(app, monkeypatch):
    existing = event("existing", "12.01.26")
    failed = event("failed", "11.06.26")
    succeeded = event("succeeded", "11.07.26")
    app.WriteCurrentEvents([existing])
    monkeypatch.setattr(app, "ListFilesInPublicFolder", lambda _: [
        remote(failed), remote(succeeded), remote(existing)
    ])
    download = MagicMock(side_effect=[None, succeeded["filename"], failed["filename"]])
    monkeypatch.setattr(app, "DownloadFile", download)

    app.main()
    assert app.ReadCurrentEvents() == [succeeded, existing]
    assert download.call_args_list == [
        call(failed["id"], failed["filename"]),
        call(succeeded["id"], succeeded["filename"]),
    ]

    app.main()
    assert download.call_args_list[-1] == call(failed["id"], failed["filename"])
    assert download.call_count == 3
    assert app.ReadCurrentEvents() == [failed, succeeded, existing]
