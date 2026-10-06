from commons.batch import short, task_name


def test_short_names_and_task_names():
    assert short("openai/gpt-6.1-sol") == "gpt-6_1-sol"
    assert short("openai-api/qwen/qwen3.5-27b") == "qwen3_5-27b"
    assert task_name("scenarios/hello.yaml") == "hello"
