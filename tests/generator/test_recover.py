import json

from acqlab.generator.recover import check, parse, prompt_for, question
from acqlab.generator.render import answer, render
from acqlab.generator.truth import generate


def _setup(seed=3):
    t = generate("d", "test", seed, mc=20)
    docs, evidence = render(t)
    texts = {d.id: d.render() for d in docs}
    filler = next(d.id for d in docs if d.domain == "filler")
    return t, evidence, texts, filler


def _oracle(t, evidence, texts):
    """Answers correctly when shown a fact's evidence, and 'not found' otherwise."""
    replies = {}
    for f, ev in zip(t.facts, evidence):
        want = answer(ev)
        lo, hi = want if isinstance(want, tuple) else (want, want)
        replies[prompt_for([texts[d] for d in ev.docs], question(f.trap, f.variant))] = {"low": lo, "high": hi}
    return lambda p, schema=None: (json.dumps(replies.get(p, {"low": None, "high": None})), 3)


def test_parse_reads_json_even_with_surrounding_text():
    assert parse('Sure: {"low": 1.5, "high": 2}') == (1.5, 2)
    assert parse("no json") == (None, None)
    assert parse('{"low": null, "high": null}') == (None, None)
    assert parse('{"low": "1.5", "high": "2"}') == (None, None)
    assert parse('{"low": true, "high": 1}') == (None, 1.0)
    assert parse('[1, 2]') == (None, None)


def test_a_correct_extractor_passes():
    t, evidence, texts, filler = _setup()
    problems, tokens = check(t, evidence, texts, _oracle(t, evidence, texts), filler)
    assert problems == [] and tokens == 3 * 2 * len(t.facts)


def test_wrong_answers_and_answers_found_in_filler_both_fail():
    t, evidence, texts, filler = _setup()
    problems, _ = check(t, evidence, texts, lambda p, schema=None: ('{"low": 999, "high": 999}', 0), filler)
    assert len(problems) == 2 * len(t.facts)


def test_non_numeric_answers_are_treated_as_not_found():
    t, evidence, texts, filler = _setup()
    problems, _ = check(t, evidence, texts, lambda p, schema=None: ('{"low": "x", "high": "y"}', 0), filler)
    assert len(problems) >= len(t.facts)
