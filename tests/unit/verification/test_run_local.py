from scripts.run_local import build_environment


def test_explicit_project_env_overrides_unrelated_shell_key(tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=project-test-key\nER_MODEL_TIMEOUT=60\n")
    environment = build_environment(
        tmp_path, {"OPENAI_API_KEY": "unrelated-shell-key", "PATH": "bin"}
    )
    assert environment["OPENAI_API_KEY"] == "project-test-key"
    assert environment["PATH"] == "bin"
    assert environment["ER_MODEL_TIMEOUT"] == "60"


def test_environment_only_startup_and_explicit_empty_key(tmp_path):
    assert (
        build_environment(tmp_path, {"OPENAI_API_KEY": "exported"})["OPENAI_API_KEY"] == "exported"
    )
    (tmp_path / ".env").write_text("OPENAI_API_KEY=\n")
    assert build_environment(tmp_path, {"OPENAI_API_KEY": "exported"})["OPENAI_API_KEY"] == ""
