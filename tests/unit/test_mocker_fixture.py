from __future__ import annotations


def _foo() -> int:
    return 1


def test_mocker_fixture_can_patch(mocker) -> None:
    patched = mocker.patch(__name__ + "._foo", return_value=2)
    assert _foo() == 2
    # Both pytest-mock and our mini mocker return a Mock-like object here.
    patched.assert_called_once()

