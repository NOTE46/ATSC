import csv
import json
import pytest
import control


@pytest.mark.unit
def test_controlfun_return_format(make_lane_data):
    """Ensure controlfun returns exact contract schema."""
    data = make_lane_data([5, 2])
    res = control.controlfun(data, 2)
    assert isinstance(res, dict)
    assert "lane_no" in res
    assert res["signal"] == "Green"
    assert isinstance(res["lane_no"], int)


@pytest.mark.unit
def test_reset_control_clears_state(make_lane_data):
    """reset_control must clear wait counts and last active lane."""
    data = make_lane_data([10, 2])
    control.controlfun(data, 2)
    assert control._last_lane is not None
    assert len(control._wait_counts) > 0

    control.reset_control()
    assert control._last_lane is None
    assert len(control._wait_counts) == 0


@pytest.mark.unit
def test_tier1_ambulance_over_firetruck(make_lane_data):
    """Ambulance (prio 2) must win over Firetruck (prio 1) regardless of density."""
    data = make_lane_data([2, 50], ["ambulance", "firetruck"])
    res = control.controlfun(data, 2)
    assert res["lane_no"] == 0


@pytest.mark.unit
def test_tier1_firetruck_over_normal(make_lane_data):
    """Firetruck (prio 1) must win over normal traffic (prio 0)."""
    data = make_lane_data([100, 1], ["none", "firetruck"])
    res = control.controlfun(data, 2)
    assert res["lane_no"] == 1


@pytest.mark.unit
def test_tier1_two_ambulances_tiebreak_by_density(make_lane_data):
    """When multiple ambulances are present, higher density wins."""
    data = make_lane_data([5, 12], ["ambulance", "ambulance"])
    res = control.controlfun(data, 2)
    assert res["lane_no"] == 1


@pytest.mark.unit
def test_tier1_legacy_ambulance_boolean_fallback():
    """Legacy dict with {"density": 5, "ambulance": True} must be recognized as ambulance."""
    data = {
        0: {"density": 10, "ambulance": False},
        1: {"density": 2, "ambulance": True},
    }
    res = control.controlfun(data, 2)
    assert res["lane_no"] == 1


@pytest.mark.unit
def test_tier2_cooldown_prevents_back_to_back_green(make_lane_data):
    """An active lane with traffic cannot get back-to-back green if another lane has traffic."""
    # Round 1: Lane 0 wins with higher density
    data = make_lane_data([10, 5])
    res1 = control.controlfun(data, 2)
    assert res1["lane_no"] == 0

    # Round 2: Lane 0 still has traffic, but Lane 1 must get green due to cooldown
    data2 = make_lane_data([10, 5])
    res2 = control.controlfun(data2, 2)
    assert res2["lane_no"] == 1


@pytest.mark.unit
def test_tier2_starving_lane_gets_priority(make_lane_data):
    """A lane waiting >= lanes cycles with traffic must trigger starvation override."""
    # 3 lanes
    lanes = 3
    # Manually set high wait count for lane 2
    control._wait_counts[0] = 0
    control._wait_counts[1] = 0
    control._wait_counts[2] = lanes  # Starving!
    control._last_lane = 0

    # Lane 1 has high density 50, but Lane 2 is starving with density 3
    data = make_lane_data([0, 50, 3])
    res = control.controlfun(data, lanes)
    assert res["lane_no"] == 2


@pytest.mark.unit
def test_tier3_weighted_density_calculation(make_lane_data):
    """Normal operation calculates score as density + (wait_count * 3)."""
    # Lane 0: density 10, wait 0 -> score 10
    # Lane 1: density 6, wait 2 -> score 6 + 6 = 12 -> wins
    control._wait_counts = {0: 0, 1: 2}
    control._last_lane = None
    data = make_lane_data([10, 6])
    res = control.controlfun(data, 2)
    assert res["lane_no"] == 1


@pytest.mark.unit
def test_zero_traffic_rotates_fairly(make_lane_data):
    """When all lanes have zero traffic, controller rotates from last active lane."""
    control._last_lane = 0
    data = make_lane_data([0, 0, 0])
    res = control.controlfun(data, 3)
    assert res["lane_no"] == 1

    res2 = control.controlfun(data, 3)
    assert res2["lane_no"] == 2


@pytest.mark.scenario
def test_starvation_prevention_over_multiple_rounds(make_lane_data):
    """Simulate a busy highway vs a side street to confirm side street never starves."""
    lanes = 2
    # Lane 0 has constant heavy traffic (20), Lane 1 has modest traffic (2)
    data = make_lane_data([20, 2])
    lane1_greens = 0

    for _ in range(6):
        res = control.controlfun(data, lanes)
        if res["lane_no"] == 1:
            lane1_greens += 1

    # Cooldown and anti-starvation ensure Lane 1 gets green multiple times
    assert lane1_greens >= 2


@pytest.mark.unit
@pytest.mark.parametrize("raw_cfg,expected", [
    ('{"starvation_threshold": 3}', 3),
    ('{}', 4),
    ('{"starvation_threshold": null}', 4),
    ('{"starvation_threshold": 0}', 4),
    ('{"starvation_threshold": true}', 4),
    ('{invalid json', 4),
])
def test_load_starvation_threshold_fallbacks(tmp_path, monkeypatch, raw_cfg, expected):
    """_load_starvation_threshold returns the configured value or falls back to lanes."""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(raw_cfg, encoding="utf-8")
    monkeypatch.setattr(control, "__file__", str(tmp_path / "control.py"))

    assert control._load_starvation_threshold(4) == expected


@pytest.mark.unit
def test_tier2_threshold_3_on_four_lanes(make_lane_data, tmp_path, monkeypatch):
    """Tier 2 starvation requires wait_count >= configured threshold 3 on 4 lanes."""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"starvation_threshold": 3}), encoding="utf-8")
    monkeypatch.setattr(control, "__file__", str(tmp_path / "control.py"))

    lanes = 4
    data = make_lane_data([50, 1, 1, 5])

    # Lane 3 is one cycle shy of starvation: higher-density lane 0 wins Tier 3.
    control._wait_counts = {0: 0, 1: 0, 2: 0, 3: 2}
    control._last_lane = None
    res_not_starving = control.controlfun(data, lanes)
    assert res_not_starving["lane_no"] == 0

    # At exactly the threshold, Lane 3 wins Tier 2 despite its lower density.
    control._wait_counts = {0: 0, 1: 0, 2: 0, 3: 3}
    control._last_lane = None
    res_starving = control.controlfun(data, lanes)
    assert res_starving["lane_no"] == 3


def _read_log_rows(path=None):
    target = path or control.DECISION_LOG_PATH
    with open(target, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


@pytest.mark.unit
def test_decision_log_schema_tiers_and_legacy_emergency(make_lane_data):
    """CSV headers and rows record all tiers, lane attributes, and legacy ambulance fallback."""
    assert control.controlfun(make_lane_data([5, 2], ["ambulance", "none"]), 2)["lane_no"] == 0

    legacy = {
        0: {"density": 10, "emergency_type": "none"},
        1: {"density": 2, "ambulance": True},
    }
    assert control.controlfun(legacy, 2)["lane_no"] == 1

    control.reset_control()
    control._wait_counts = {0: 0, 1: 0, 2: 3}
    control._last_lane = 0
    assert control.controlfun(make_lane_data([0, 50, 3]), 3)["lane_no"] == 2

    control.reset_control()
    control._wait_counts = {0: 0, 1: 2}
    control._last_lane = None
    assert control.controlfun(make_lane_data([10, 6]), 2)["lane_no"] == 1

    control.reset_control()
    control._last_lane = 0
    assert control.controlfun(make_lane_data([0, 0, 0]), 3)["lane_no"] == 1

    rows = _read_log_rows()
    assert rows[0] == control.LOG_HEADERS
    assert rows.count(control.LOG_HEADERS) == 1
    assert all(len(row) == len(control.LOG_HEADERS) for row in rows)

    data_rows = rows[1:]
    assert len(data_rows) == 5
    assert [row[1] for row in data_rows] == ["2", "2", "3", "2", "3"]
    assert [row[2] for row in data_rows] == ["0", "1", "2", "1", "1"]
    assert [row[3] for row in data_rows] == [
        "emergency", "emergency", "starvation", "density", "rotation"
    ]
    assert [row[4] for row in data_rows] == [
        "0:5|1:2",
        "0:10|1:2",
        "0:0|1:50|2:3",
        "0:10|1:6",
        "0:0|1:0|2:0",
    ]
    assert [row[5] for row in data_rows] == [
        "0:ambulance|1:none",
        "0:none|1:ambulance",
        "0:none|1:none|2:none",
        "0:none|1:none",
        "0:none|1:none|2:none",
    ]
    assert all(row[0] for row in data_rows)

    before = len(rows)
    assert control.controlfun({}, 0) == {"lane_no": 0, "signal": "Green"}
    assert len(_read_log_rows()) == before


@pytest.mark.unit
def test_decision_log_records_pre_update_wait_counts(make_lane_data):
    """The starvation winner is logged with its wait count from before the decision."""
    control._wait_counts = {0: 0, 1: 0, 2: 3}
    control._last_lane = 0

    assert control.controlfun(make_lane_data([0, 50, 3]), 3)["lane_no"] == 2
    assert control._wait_counts[2] == 0

    rows = _read_log_rows()
    assert rows[0] == control.LOG_HEADERS
    assert len(rows) == 2
    assert rows[1][6] == "0:0|1:0|2:3"


@pytest.mark.unit
def test_decision_log_rollover_overwrites_backup(monkeypatch, make_lane_data):
    """The log rotates at MAX_LOG_BYTES and replaces an existing backup cleanly."""
    monkeypatch.setattr(control, "MAX_LOG_BYTES", 120)
    data = make_lane_data([10, 5])
    control.controlfun(data, 2)
    control.controlfun(data, 2)

    log_path = control.DECISION_LOG_PATH
    backup_path = log_path.with_name(log_path.name + ".1")
    assert backup_path.exists()
    assert len(_read_log_rows()) == 2
    assert len(_read_log_rows(backup_path)) == 2

    backup_before = backup_path.read_bytes()
    control.controlfun(make_lane_data([1, 1]), 2)
    backup_after = backup_path.read_bytes()

    assert backup_after != backup_before
    rows = _read_log_rows()
    backup_rows = _read_log_rows(backup_path)
    assert rows[0] == control.LOG_HEADERS and len(rows) == 2
    assert backup_rows[0] == control.LOG_HEADERS and len(backup_rows) == 2


@pytest.mark.unit
def test_decision_log_none_path_is_noop(monkeypatch, make_lane_data):
    """A None log path disables logging without affecting the decision."""
    monkeypatch.setattr(control, "DECISION_LOG_PATH", None)
    assert control.controlfun(make_lane_data([5, 2]), 2) == {"lane_no": 0, "signal": "Green"}


@pytest.mark.unit
def test_decision_log_directory_path_does_not_crash(monkeypatch, tmp_path, make_lane_data):
    """Opening a directory as the log file is swallowed and the decision still returns."""
    monkeypatch.setattr(control, "DECISION_LOG_PATH", tmp_path)
    assert control.controlfun(make_lane_data([5, 2]), 2) == {"lane_no": 0, "signal": "Green"}


@pytest.mark.unit
def test_decision_log_rollover_error_does_not_crash(monkeypatch, make_lane_data):
    """A rotation OSError is swallowed and the decision still returns."""
    log_path = control.DECISION_LOG_PATH
    monkeypatch.setattr(control, "MAX_LOG_BYTES", 10)
    log_path.write_bytes(b"x" * 20)

    def fail_replace(*args, **kwargs):
        raise OSError("disk error")

    monkeypatch.setattr(control.os, "replace", fail_replace)
    assert control.controlfun(make_lane_data([1, 9]), 2) == {"lane_no": 1, "signal": "Green"}
