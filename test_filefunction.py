import ast

import pytest

import filefunction


@pytest.mark.parametrize(
    "filename,date,bands,extension",
    [
        ("11.06.26 Maneater, Demansia, Culmination.jpg", "11.06.26", "Maneater, Demansia, Culmination", "jpg"),
        ("01.02.26 One Band.png", "01.02.26", "One Band", "png"),
        ("12.31.26 Band.Name.live.JPG", "12.31.26", "Band.Name.live", "JPG"),
        ("11.06.26\tBand.jpg", "11.06.26", "Band", "jpg"),
        # The current parser checks date format, not calendar validity.
        ("99.99.99 Band.jpg", "99.99.99", "Band", "jpg"),
    ],
)
def test_split_filename(filename, date, bands, extension):
    assert filefunction.SplitFilename(filename, "file-123") == {
        "filename": filename,
        "date": date,
        "bandnames": bands,
        "id": "file-123",
        "extension": extension,
    }


@pytest.mark.parametrize(
    "filename",
    [
        "",
        "poster.jpg",
        "11-06-26 Band.jpg",
        "1.06.26 Band.jpg",
        "11.06.2026 Band.jpg",
        "11.06.26Band.jpg",
        "11.06.26 .jpg",
        "11.06.26 Band",
        "11.06.26 Band.",
    ],
)
def test_split_filename_rejects_invalid_format(filename):
    assert filefunction.SplitFilename(filename, "file-123") is None


def test_create_files_dictionary_empty():
    assert filefunction.CreateFilesDictonary([]) == []


def test_create_files_dictionary_filters_invalid_items_and_preserves_order():
    items = [
        {"name": "11.06.26 First.jpg", "id": "first"},
        {},
        {"name": "11.06.26 Missing ID.jpg"},
        {"id": "missing-name"},
        {"name": "", "id": "empty-name"},
        {"name": "11.06.26 Empty ID.jpg", "id": ""},
        {"name": None, "id": "null-name"},
        {"name": "11.06.26 Null ID.jpg", "id": None},
        {"name": "unparseable.jpg", "id": "bad-format"},
        {"name": "12.07.26 Second.png", "id": "second"},
    ]

    assert filefunction.CreateFilesDictonary(items) == [
        {"filename": "11.06.26 First.jpg", "date": "11.06.26", "bandnames": "First", "id": "first", "extension": "jpg"},
    ]


def test_main_reports_6_files(capsys):
    filefunction.main()

    lines = capsys.readouterr().out.splitlines()
    assert lines[-1] == "Processed 6 events"
    events = [ast.literal_eval(line) for line in lines[:-1]]
    assert len(events) == 6
    assert all(item["extension"] == "jpg" for item in events)


@pytest.mark.parametrize("suffix", ["png", "jpeg", "JPG", "gif", "txt", ""])
def test_create_files_dictionary_skips_other_extensions(suffix):
    name = "11.06.26 Band" + ("." + suffix if suffix else "")
    assert filefunction.CreateFilesDictonary([{"name": name, "id": "id"}]) == []


def test_create_files_dictionary_preserves_multiple_valid_events():
    names = ["12.01.26 Second.jpg", "11.01.26 First.jpg"]
    items = [{"name": name, "id": str(i)} for i, name in enumerate(names)]
    assert filefunction.CreateFilesDictonary(items) == [
        filefunction.SplitFilename(item["name"], item["id"]) for item in items
    ]


def test_main_reports_processing_error(monkeypatch, capsys):
    def fail(items):
        raise RuntimeError("parser failed")

    monkeypatch.setattr(filefunction, "CreateFilesDictonary", fail)
    filefunction.main()
    assert capsys.readouterr().out == (
        "An error occurred: parser failed\nProcessed 6 events\n"
    )
