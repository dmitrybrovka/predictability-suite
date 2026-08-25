from pathlib import Path

from predictability.core.config import AppConfig


def test_load_default_yaml(tmp_path: Path) -> None:
    path = tmp_path / "cfg.yaml"
    path.write_text(
        "slip:\n  unit: calendar_days\nmodel:\n  min_history: 7\nfactors:\n"
        "  - name: team_bias\n    enabled: true\n    params: {shrinkage_k: 3}\n",
        encoding="utf-8",
    )
    cfg = AppConfig.load(path)
    assert cfg.slip_unit == "calendar_days"
    assert cfg.min_history == 7
    assert cfg.factor_enabled("team_bias") is True
    assert cfg.factor_params("team_bias")["shrinkage_k"] == 3
    assert cfg.holidays_path is None


def test_holidays_path_from_factor_params(tmp_path: Path) -> None:
    hol = tmp_path / "h.yaml"
    cfg = AppConfig(
        {
            "factors": [
                {
                    "name": "capacity_calendar",
                    "enabled": True,
                    "params": {"holidays_path": str(hol)},
                }
            ]
        }
    )
    assert cfg.holidays_path == hol


def test_holidays_path_from_slip_overrides_factor(tmp_path: Path) -> None:
    slip_hol = tmp_path / "slip.yaml"
    factor_hol = tmp_path / "factor.yaml"
    slip_hol.write_text("holidays: []\n", encoding="utf-8")
    factor_hol.write_text("holidays: []\n", encoding="utf-8")
    cfg = AppConfig(
        {
            "slip": {"holidays_path": str(slip_hol)},
            "factors": [
                {
                    "name": "capacity_calendar",
                    "enabled": True,
                    "params": {"holidays_path": str(factor_hol)},
                }
            ],
        }
    )
    assert cfg.holidays_path == slip_hol


def test_load_json(tmp_path: Path) -> None:
    path = tmp_path / "cfg.json"
    path.write_text('{"model": {"backend": "empirical_bayes"}}', encoding="utf-8")
    cfg = AppConfig.load(path)
    assert cfg.backend == "empirical_bayes"
