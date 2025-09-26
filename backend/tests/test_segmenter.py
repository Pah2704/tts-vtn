from backend.modules.segmenter import segment_text, SegmentationConfig


def test_segmenter_punctuation_merge_max() -> None:
    text = "Hello world! A. B. This is a long sentence that should be split eventually."
    cfg = SegmentationConfig(strategy="punctuation", mergeShortBelow=4, maxChunkChars=30)
    parts = segment_text(text, cfg)
    assert all(len(part) <= 30 for part in parts)
    assert any("A. B." in part or "A. B" in part for part in parts)
