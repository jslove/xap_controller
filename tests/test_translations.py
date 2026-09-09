"""strings.json and translations/en.json have to survive Home Assistant's formatter.

Translations are rendered through intl-messageformat, where {...} is a placeholder.
A literal brace - a JSON example in help text, say - is parsed as a malformed argument
and the whole string is replaced in the UI by "Translation error: MALFORMED_ARGUMENT",
taking the real text with it. Nothing else in this suite renders a translation, so
without this the only way to find out is to look at the form.
"""

import json
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
FILES = ["strings.json", "translations/en.json"]


def _load(name):
    return json.loads((_ROOT / name).read_text())


def _strings(obj, path=""):
    """Every leaf string, with the dotted path that reaches it."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(obj, str):
        yield path, obj


@pytest.mark.parametrize("name", FILES)
def test_no_literal_braces_in_any_string(name):
    offenders = [(p, s) for p, s in _strings(_load(name)) if "{" in s or "}" in s]
    assert not offenders, "\n".join(
        f"{name}{p}: {s!r}" for p, s in offenders
    ) + "\n\nBraces are placeholders; write the example without them."


@pytest.mark.parametrize("name", FILES)
def test_it_is_valid_json(name):
    _load(name)


def test_the_two_files_have_the_same_keys():
    """en.json is the one Home Assistant actually loads; strings.json is the source.

    They are maintained by hand in parallel, so a key added to one and not the other
    shows up as an untranslated slug in the UI rather than as any kind of error.
    """
    keys = [{p for p, _ in _strings(_load(n))} for n in FILES]
    assert keys[0] == keys[1], (
        f"only in {FILES[0]}: {sorted(keys[0] - keys[1])}\n"
        f"only in {FILES[1]}: {sorted(keys[1] - keys[0])}"
    )
