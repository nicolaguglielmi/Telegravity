"""Tests for workspace discovery & label->path resolution."""

import json

from telegravity.workspaces import (
    import_antigravity_projects,
    parse_workspaces_file,
    resolve_workspaces,
)


def _write_project(projects_dir, name, folder_uri):
    (projects_dir / f"{name.lower()}.json").write_text(
        json.dumps(
            {
                "id": name.lower(),
                "name": name,
                "projectResources": {"resources": [{"folderUri": folder_uri}]},
            }
        )
    )


def test_import_maps_name_to_path_and_skips_missing(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    proj = tmp_path / "MyProj"
    proj.mkdir()
    _write_project(projects, "MyProj", f"file://{proj}")
    _write_project(projects, "Gone", "file:///nope/missing/xyz")
    result = import_antigravity_projects(projects)
    assert result == {"MyProj": str(proj.resolve())}


def test_import_missing_dir_returns_empty(tmp_path):
    assert import_antigravity_projects(tmp_path / "does-not-exist") == {}


def test_import_tolerates_bad_or_incomplete_json(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "bad.json").write_text("{not json")
    (projects / "noname.json").write_text(
        json.dumps({"projectResources": {"resources": [{"folderUri": "file:///x"}]}})
    )
    assert import_antigravity_projects(projects) == {}


def test_parse_file_labels_paths_and_comments(tmp_path):
    proj = tmp_path / "Proj"
    proj.mkdir()
    f = tmp_path / "workspaces.txt"
    f.write_text(f"# a comment\n\nBare\nWithPath={proj}\nBadPath=/nope/missing\n")
    parsed = parse_workspaces_file(f)
    assert parsed["Bare"] is None
    assert parsed["WithPath"] == str(proj.resolve())
    assert parsed["BadPath"] is None  # non-existent dir -> no path


def test_parse_file_missing_returns_empty(tmp_path):
    assert parse_workspaces_file(tmp_path / "nope.txt") == {}


def test_resolve_merges_all_sources(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    a = tmp_path / "A"
    a.mkdir()
    _write_project(projects, "A", f"file://{a}")
    b = tmp_path / "B"
    b.mkdir()
    f = tmp_path / "workspaces.txt"
    f.write_text(f"B={b}\nC\n")
    labels, paths = resolve_workspaces(["A", "D"], f, projects, autoimport=True)
    assert labels == ["A", "B", "C", "D"]
    assert paths["A"] == str(a.resolve())
    assert paths["B"] == str(b.resolve())
    assert "C" not in paths  # bare label, no path anywhere
    assert "D" not in paths


def test_resolve_autoimport_off(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    a = tmp_path / "A"
    a.mkdir()
    _write_project(projects, "A", f"file://{a}")
    labels, paths = resolve_workspaces([], tmp_path / "none.txt", projects, autoimport=False)
    assert labels == []
    assert paths == {}


def test_resolve_base_dir_fallback(tmp_path):
    base = tmp_path / "dev"
    base.mkdir()
    (base / "Foo").mkdir()
    f = tmp_path / "workspaces.txt"
    f.write_text("Foo\nGhost\n")
    labels, paths = resolve_workspaces(
        [], f, tmp_path / "noproj", autoimport=False, base_dir=str(base)
    )
    assert labels == ["Foo", "Ghost"]
    assert paths["Foo"] == str((base / "Foo").resolve())
    assert "Ghost" not in paths  # no dir under base


def test_resolve_explicit_path_overrides_autoimport(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    auto = tmp_path / "auto"
    auto.mkdir()
    _write_project(projects, "X", f"file://{auto}")
    manual = tmp_path / "manual"
    manual.mkdir()
    f = tmp_path / "workspaces.txt"
    f.write_text(f"X={manual}\n")
    labels, paths = resolve_workspaces([], f, projects, autoimport=True)
    assert labels == ["X"]
    assert paths["X"] == str(manual.resolve())  # explicit Label=/path wins
