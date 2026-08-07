from pathlib import Path

from framework.config import load_config
from framework.domain import expand_feature_packs


def test_multi_project_loader():
    root = Path(__file__).resolve().parents[1]
    cfg = load_config(root / "app")
    assert {p.slug for p in cfg.projects} == {"app1", "app2"}
    app1 = next(p for p in cfg.projects if p.slug == "app1")
    assert app1.api_prefix == "/api/app1/v1"
    assert app1.cache.enabled is True
    assert any(r.path == "notes" for r in app1.resources)


def test_feature_pack_expansion():
    root = Path(__file__).resolve().parents[1]
    cfg = load_config(root / "app")
    app1 = next(p for p in cfg.projects if p.slug == "app1")
    expand_feature_packs(app1)
    paths = {r.path for r in app1.resources}
    assert "messaging/messages" in paths
    assert "social/posts" in paths
    assert "gaming/leaderboard" in paths
