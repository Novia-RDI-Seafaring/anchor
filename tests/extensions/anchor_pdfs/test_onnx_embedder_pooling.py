"""The ONNX embedder pools the way each model's own config says, and batches by length.

bge pools the CLS token; bekko mean-pools. Reading the mode from the repo's
``1_Pooling/config.json`` keeps both right without a per-model table, and an
unknown mode must fail rather than produce vectors that rank badly.

Long regions cost memory with the square of their length in the exported
graphs, so batches are packed by length and a long text never pads short ones.
"""
from __future__ import annotations

import pytest

from anchor.extensions.anchor_pdfs.infra.llm.onnx_embedder import (
    _ATTENTION_BUDGET,
    _MAX_BATCH,
    MAX_TOKENS_CAP,
    OnnxEmbedder,
    _length_batches,
    _pooling_mode,
)


def test_pooling_mode_reads_cls_and_mean():
    assert _pooling_mode({"pooling_mode_cls_token": True}) == "cls"
    assert _pooling_mode({"pooling_mode_cls_token": False, "pooling_mode_mean_tokens": True}) == "mean"


def test_pooling_mode_refuses_what_it_cannot_compute():
    with pytest.raises(ValueError, match="unsupported pooling"):
        _pooling_mode({"pooling_mode_max_tokens": True})


def test_every_text_lands_in_exactly_one_batch():
    lengths = [5, 2048, 30, 7, 1500, 12] * 20

    batches = _length_batches(lengths)

    assert sorted(i for b in batches for i in b) == list(range(len(lengths)))


def test_batches_stay_within_the_attention_budget_and_row_cap():
    lengths = [5, 2048, 30, 7, 1500, 12, 900, 900, 900] * 10

    for batch in _length_batches(lengths):
        longest = max(lengths[i] for i in batch)
        assert len(batch) <= _MAX_BATCH
        assert len(batch) == 1 or len(batch) * longest**2 <= _ATTENTION_BUDGET


def test_a_text_at_the_cap_runs_alone():
    batches = _length_batches([10, MAX_TOKENS_CAP, 12])

    assert [1] in batches


def test_bge_falls_back_to_its_published_config_when_the_cache_lacks_it(monkeypatch):
    """An offline cache prefetched by an older release holds no pooling config."""
    import huggingface_hub

    def download(repo, filename):
        if filename in ("1_Pooling/config.json", "sentence_bert_config.json"):
            raise FileNotFoundError(filename)
        return f"/cache/{repo}/{filename}"

    class FakeTokenizer:
        def enable_truncation(self, max_length):
            self.max_length = max_length

        def enable_padding(self):
            pass

    import onnxruntime
    import tokenizers

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    monkeypatch.setattr(tokenizers.Tokenizer, "from_file", staticmethod(lambda _p: FakeTokenizer()))
    monkeypatch.setattr(onnxruntime, "InferenceSession", lambda *_a, **_k: object())

    emb = OnnxEmbedder("BAAI/bge-small-en-v1.5")
    emb._ensure_loaded()
    assert (emb._pooling, emb.max_tokens) == ("cls", 512)

    other = OnnxEmbedder("someone/unknown-model")
    with pytest.raises(FileNotFoundError):
        other._ensure_loaded()
