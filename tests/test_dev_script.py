from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_dev_script_uses_port_preflight_and_fixed_vite_port() -> None:
    script = (ROOT_DIR / "scripts" / "dev.sh").read_text()

    assert "wait -n" not in script
    assert "ensure_port_available" in script
    assert "--strictPort" in script
