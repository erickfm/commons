from commons.judge import Judge


def test_cached_answers_need_no_model(tmp_path):
    path = tmp_path / "j.json"
    path.write_text('{"is it?": "yes"}')
    assert Judge(path)("is it?", ["yes", "no"]) == "yes"
