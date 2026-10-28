from common.config import parse_env_file


def test_parse_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "\n"
        "INFLUX_ORG=portran\n"
        "INFLUX_TOKEN = abc=def\n"
        'QUOTED="hello world"\n'
        "SINGLE='x'\n"
        "EMPTY=\n"
        "not a pair\n",
        encoding="utf-8",
    )
    assert parse_env_file(env) == {
        "INFLUX_ORG": "portran",
        "INFLUX_TOKEN": "abc=def",
        "QUOTED": "hello world",
        "SINGLE": "x",
        "EMPTY": "",
    }


def test_load_env_fills_missing_keys_from_example(tmp_path, monkeypatch):
    import os
    from common.config import load_env

    env = tmp_path / ".env"
    example = tmp_path / ".env.example"
    env.write_text("PORTRAN_TEST_A=from-env\n", encoding="utf-8")
    example.write_text("PORTRAN_TEST_A=from-example\nPORTRAN_TEST_B=only-in-example\n", encoding="utf-8")
    monkeypatch.delenv("PORTRAN_TEST_A", raising=False)
    monkeypatch.delenv("PORTRAN_TEST_B", raising=False)
    monkeypatch.setenv("PORTRAN_TEST_C", "from-shell")
    load_env(env, example)
    assert os.environ["PORTRAN_TEST_A"] == "from-env"
    assert os.environ["PORTRAN_TEST_B"] == "only-in-example"
    assert os.environ["PORTRAN_TEST_C"] == "from-shell"
    monkeypatch.delenv("PORTRAN_TEST_A")
    monkeypatch.delenv("PORTRAN_TEST_B")
