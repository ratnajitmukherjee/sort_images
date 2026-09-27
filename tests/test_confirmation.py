"""Tests for the interactive confirmation guard and interrupt handling."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from sort_images import cli
from sort_images.cli import EXIT_ABORTED, EXIT_OK, _confirm, main


class _FakeStdin:
    def __init__(self, tty: bool) -> None:
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.fixture
def interactive(monkeypatch: pytest.MonkeyPatch):
    """Pretend a terminal is attached, with a scripted answer."""

    def _setup(answer: str | type[BaseException]) -> None:
        monkeypatch.setattr(cli.sys, "stdin", _FakeStdin(tty=True))

        def _input(prompt: str = "") -> str:
            if isinstance(answer, type) and issubclass(answer, BaseException):
                raise answer()
            return answer

        monkeypatch.setattr("builtins.input", _input)

    return _setup


@pytest.mark.parametrize("answer", ["y", "Y", "yes", "YES", " yes "])
def test_affirmative_answers_confirm(interactive, answer: str) -> None:
    interactive(answer)
    assert _confirm("Move?") is True


@pytest.mark.parametrize("answer", ["n", "no", "", "maybe", "q"])
def test_anything_else_declines(interactive, answer: str) -> None:
    interactive(answer)
    assert _confirm("Move?") is False


@pytest.mark.parametrize("interrupt", [EOFError, KeyboardInterrupt])
def test_interrupting_the_prompt_declines(interactive, interrupt) -> None:
    interactive(interrupt)
    assert _confirm("Move?") is False


def test_no_terminal_proceeds_without_asking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-interactive runs cannot prompt, so they proceed.

    Moves are reversible and never overwrite, so this is safe; --dry-run is
    there for anyone who wants to look first.
    """
    monkeypatch.setattr(cli.sys, "stdin", _FakeStdin(tty=False))
    assert _confirm("Move?") is True


def test_declining_aborts_without_changing_anything(
    tmp_path: Path, jpeg_factory, interactive, capsys: pytest.CaptureFixture[str]
) -> None:
    source = jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))
    interactive("n")

    exit_code = main(["-i", str(tmp_path)])

    assert exit_code == EXIT_ABORTED
    assert source.exists()
    assert not (tmp_path / "2023-05").exists()
    assert "Aborted" in capsys.readouterr().out


def test_accepting_proceeds(tmp_path: Path, jpeg_factory, interactive) -> None:
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14))
    interactive("y")

    assert main(["-i", str(tmp_path)]) == EXIT_OK
    assert (tmp_path / "2023-05" / "IMG_0001.jpg").is_file()


def test_no_prompt_when_there_is_nothing_to_move(
    tmp_path: Path, jpeg_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Already-sorted folders must not ask a pointless question."""
    jpeg_factory("IMG_0001.jpg", datetime(2023, 5, 14), root=tmp_path / "2023-05")

    def _explode(prompt: str = "") -> str:  # pragma: no cover - must not run
        raise AssertionError("should not have prompted")

    monkeypatch.setattr(cli.sys, "stdin", _FakeStdin(tty=True))
    monkeypatch.setattr("builtins.input", _explode)

    assert main(["-i", str(tmp_path), "--recursive"]) == EXIT_OK


def test_keyboard_interrupt_during_run_is_handled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "find_images", _interrupt)

    assert main(["-i", str(tmp_path)]) == EXIT_ABORTED
    assert "Interrupted" in capsys.readouterr().err
