from framework.config import load_config


def test_sample_config_loads():
    cfg = load_config()
    assert cfg.api_prefix.startswith("/")
    assert cfg.resources
    assert cfg.resources[0].path == "notes"
