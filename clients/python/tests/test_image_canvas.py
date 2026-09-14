from hydracept.cli.image_canvas import preflight_image_canvas


def test_image_canvas_allows_default_and_large_enough_sizes() -> None:
    assert preflight_image_canvas("image.generate.v1", {"prompt": "icon"}) is None
    assert preflight_image_canvas("image.generate.v1", {"width": 816, "height": 816}) is None
    assert preflight_image_canvas("text.general.fast.v1", {"width": 512, "height": 512}) is None


def test_image_canvas_rejects_undersized_explicit_canvas() -> None:
    blocked = preflight_image_canvas(
        "image.generate.v1",
        {"input": {"prompt": "potion", "width": 512, "height": 512}},
    )
    assert blocked is not None
    assert blocked["code"] == "InvalidInput"
    assert "655360" in blocked["message"]
    assert "816" in blocked["message"]
