import json
import re

from acqlab.generator.documents import Slot
from acqlab.generator.prose import ATTEMPTS, acceptable, doc_prompt, doc_schema, fill, prompt_for
from acqlab.generator.render import render
from acqlab.generator.truth import generate

DOCS = render(generate("d0", "test", 0, mc=20))[0]
WITH_SLOTS = [d for d in DOCS if any(isinstance(b, Slot) for b in d.blocks)]
NUMBERS = re.compile(r"\$[\d,.]+M|[\d.]+%")
CONTEXT = "Harbor Tools, a machinery business (deal test-000)"


def _slots(doc):
    return [b for b in doc.blocks if isinstance(b, Slot)]


def _good(doc):
    return json.dumps({s.id: "In summary, " + s.template for s in _slots(doc)})


class Fake:
    """Answers whole-document prompts from a table, and counts every call."""

    def __init__(self, doc_reply, retry_reply="Revenue rose 12 percent."):
        self.doc_reply, self.retry_reply, self.calls = doc_reply, retry_reply, []

    def __call__(self, prompt, schema=None):
        self.calls.append((prompt, schema))
        if schema is not None:
            doc = next(d for d in WITH_SLOTS if doc_prompt(d, _slots(d), CONTEXT) == prompt)
            return self.doc_reply(doc), 5
        return self.retry_reply, 1


def test_slot_ids_are_unique_within_each_document():
    for d in DOCS:
        ids = [s.id for s in _slots(d)]
        assert len(ids) == len(set(ids)), d.id


def test_one_call_per_document_writes_every_paragraph_and_keeps_every_number():
    fake = Fake(_good)
    out, tokens, fallbacks = fill(DOCS, fake, context=CONTEXT)
    assert fallbacks == 0 and len(fake.calls) == len(WITH_SLOTS) and tokens == 5 * len(WITH_SLOTS)
    for before, after in zip(DOCS, out):
        assert sorted(NUMBERS.findall(before.render())) == sorted(NUMBERS.findall(after.render()))
        assert all(s.text.startswith("In summary") for s in _slots(after))


def test_only_the_broken_paragraph_is_retried_on_its_own():
    def one_bad(doc):
        replies = json.loads(_good(doc))
        replies[_slots(doc)[0].id] = "Revenue rose 12 percent."  # digits: rejected
        return json.dumps(replies)

    fake = Fake(one_bad)
    out, _, fallbacks = fill(WITH_SLOTS[:1], fake, context=CONTEXT)
    retries = [p for p, schema in fake.calls if schema is None]
    assert fallbacks == 1 and len(retries) == ATTEMPTS - 1 and len(set(retries)) == len(retries)
    first, *rest = _slots(out[0])
    assert first.text is None and all(s.text.startswith("In summary") for s in rest)


def test_malformed_json_falls_back_paragraph_by_paragraph():
    fake = Fake(lambda doc: "not json")
    out, _, fallbacks = fill(WITH_SLOTS[:1], fake, context=CONTEXT)
    assert fallbacks == len(_slots(out[0])) and all(s.text is None for s in _slots(out[0]))


def test_document_prompt_keeps_paragraphs_separate_and_the_schema_requires_each_one():
    doc = WITH_SLOTS[0]
    prompt, schema = doc_prompt(doc, _slots(doc), CONTEXT), doc_schema(_slots(doc))
    assert "do not mention one paragraph's subject in another" in prompt and "Write no digits" in prompt
    assert all(f"- id: {s.id}" in prompt for s in _slots(doc))
    assert schema["required"] == [s.id for s in _slots(doc)] and schema["additionalProperties"] is False


def test_prompts_name_the_deal_so_identical_templates_never_share_a_cached_reply():
    doc = WITH_SLOTS[0]
    s = _slots(doc)[0]
    other = "Pine Foods, a food processing business (deal dev-007)"
    for make in (lambda c: doc_prompt(doc, _slots(doc), c), lambda c: prompt_for(doc, s, 1, c)):
        a, b = make(CONTEXT), make(other)
        assert a != b and CONTEXT in a and other in b


def test_spelled_out_numbers_are_rejected_unless_the_template_has_them():
    template = "The {{label}} is payable within twelve months of closing and was a one-time cost."
    assert acceptable("The {{label}} is due within twelve months; it was a one-time cost.", template)
    for bad in ("The {{label}} of two million dollars is due within twelve months.",
                "Half of the {{label}} is due within twelve months.", "The {{label}} rose five percent in twelve months."):
        assert not acceptable(bad, template), bad
