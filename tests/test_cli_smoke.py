import pytest

from aibox.cli import build_parser, main


def test_help_exits_zero_and_lists_all_commands(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    for command in ("run", "info", "remove-volume", "rebuild-image"):
        assert command in captured.out


@pytest.mark.parametrize("command", ["run", "info", "remove-volume", "rebuild-image"])
def test_each_subcommand_runs_and_returns_zero(command, capsys):
    assert main([command]) == 0


def test_no_args_defaults_to_run(capsys):
    assert main([]) == 0
    captured = capsys.readouterr()
    assert "aibox run" in captured.err


def test_run_accepts_all_documented_flags():
    parser = build_parser()
    args = parser.parse_args([
        "run",
        "-p", "3000:3000",
        "-p", "8000:8000",
        "-e", "NODE_ENV=development",
        "--env-file", ".env",
        "--shell", "/bin/zsh",
        "--docker-arg=--add-host=host.docker.internal:host-gateway",
        "--user", "root",
    ])
    assert args.port == ["3000:3000", "8000:8000"]
    assert args.env == ["NODE_ENV=development"]
    assert args.env_file == [".env"]
    assert args.shell == "/bin/zsh"
    assert args.docker_arg == ["--add-host=host.docker.internal:host-gateway"]
    assert args.user == "root"


def test_remove_volume_force_flag():
    parser = build_parser()
    assert parser.parse_args(["remove-volume"]).force is False
    assert parser.parse_args(["remove-volume", "--force"]).force is True
