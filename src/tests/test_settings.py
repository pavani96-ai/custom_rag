"""Check that the query model and the eval judge model are read from the environment."""

from app.config.settings import Settings


def test_judge_and_query_models_come_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "query-model")
    monkeypatch.setenv("GEMINI_JUDGE_MODEL", "judge-model")
    monkeypatch.setenv("EVAL_API_BASE_URL", "http://api:8000")

    settings = Settings(_env_file=None)

    assert settings.gemini_model == "query-model"
    assert settings.gemini_judge_model == "judge-model"
    assert settings.eval_api_base_url == "http://api:8000"


def test_judge_model_has_its_own_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.gemini_judge_model
    assert settings.gemini_judge_model != settings.gemini_model


def test_settings_read_values_from_env_file(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_JUDGE_MODEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_JUDGE_MODEL=file-judge\nPOSTGRES_PASSWORD=ignored\n")

    settings = Settings(_env_file=env_file)

    assert settings.gemini_judge_model == "file-judge"
