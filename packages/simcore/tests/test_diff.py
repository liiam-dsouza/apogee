from simcore.mission.diff import diff_missions


def test_reports_leaf_changes_in_order() -> None:
    a = {
        "meta": {"name": "L", "created_utc": "x"},
        "rocket": {"drag": {"multiplier": 1.0}, "dry_inertia": [1, 2, 3]},
    }
    b = {
        "meta": {"name": "L", "created_utc": "y"},
        "rocket": {"drag": {"multiplier": 1.1}, "dry_inertia": [1, 2, 4]},
    }
    d = diff_missions(a, b)
    assert [(x.path, x.a, x.b) for x in d] == [
        ("rocket.drag.multiplier", 1.0, 1.1),
        ("rocket.dry_inertia", [1, 2, 3], [1, 2, 4]),  # a numeric tuple is one value
    ]


def test_lists_of_objects_by_index_and_long_lists_summarised() -> None:
    dev = {"name": "Drogue", "cd_s_m2": 1.0}
    a = {"recovery": {"devices": [dev]}, "env": {"levels": list(range(30))}}
    b = {"recovery": {"devices": [dev | {"cd_s_m2": 0.6}]}, "env": {"levels": list(range(31))}}
    d = {x.path: (x.a, x.b) for x in diff_missions(a, b)}
    assert d["recovery.devices[0].cd_s_m2"] == (1.0, 0.6)
    assert d["env.levels"] == ("30 items", "31 items")


def test_added_and_removed_sections() -> None:
    d = diff_missions({"site": None}, {"site": {"elevation_m": 220}})
    assert [(x.path, x.a, x.b) for x in d] == [("site", None, {"elevation_m": 220})]
    assert diff_missions({"a": 1}, {"a": 1}) == []
