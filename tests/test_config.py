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
