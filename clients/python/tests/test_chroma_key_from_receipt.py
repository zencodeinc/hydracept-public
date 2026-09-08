"""Receipt chroma-key extraction for the image smoke contract."""

from hydracept.chroma_key_from_receipt import chroma_key_from_receipt
from hydracept.chroma_plate_key import DEFAULT_CHROMA_KEY


def test_chroma_key_from_receipt_defaults_to_magenta() -> None:
    assert chroma_key_from_receipt(None) == DEFAULT_CHROMA_KEY
    assert chroma_key_from_receipt({}) == DEFAULT_CHROMA_KEY


def test_chroma_key_from_receipt_reads_matte_metadata() -> None:
    receipt = {"media": {"matte": {"chromaKeyColor": "#00FFFF"}}}
    assert chroma_key_from_receipt(receipt) == "#00ffff"


def test_chroma_key_from_receipt_ignores_unknown_keys() -> None:
    receipt = {"matte": {"chromaKeyColor": "#ffffff"}}
    assert chroma_key_from_receipt(receipt) == DEFAULT_CHROMA_KEY
