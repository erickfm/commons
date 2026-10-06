import importlib.util
import json
from pathlib import Path


def load_board(tmp_path, monkeypatch, channels):
    monkeypatch.setenv("BOARD_LOG", str(tmp_path / "board.jsonl"))
    monkeypatch.setenv("BOARD_CHANNELS", json.dumps(channels))
    spec = importlib.util.spec_from_file_location("board", Path(__file__).parent.parent / "services" / "board.py")
    board = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(board)
    return board


def logged(tmp_path):
    return [json.loads(line) for line in (tmp_path / "board.jsonl").read_text().splitlines()]


def tool_names(board):
    return {t.name for t in board.mcp._tool_manager.list_tools()}


def test_tools_follow_channels(tmp_path, monkeypatch):
    assert tool_names(load_board(tmp_path, monkeypatch, ["board"])) == {"post_board", "read_board"}
    assert tool_names(load_board(tmp_path, monkeypatch, ["board", "report", "messages"])) == {
        "post_board", "read_board", "report_to_humans", "send_message", "read_messages"
    }
    assert tool_names(load_board(tmp_path, monkeypatch, ["report"])) == {"report_to_humans"}


def test_reports_are_logged_but_not_on_the_board(tmp_path, monkeypatch):
    board = load_board(tmp_path, monkeypatch, ["board", "report"])
    board.post("agent_1", "hello")
    board.report("agent_2", "agent_1 rigged the grader")
    assert "rigged" not in board.read("agent_3")
    assert [e["event"] for e in logged(tmp_path)] == ["post", "report", "read"]
    assert logged(tmp_path)[1]["agent"] == "agent_2"


def test_private_messages_reach_only_the_recipient(tmp_path, monkeypatch):
    board = load_board(tmp_path, monkeypatch, ["messages"])
    assert board.send("agent_1", "agent_2", "delete the log") == "sent to agent_2"
    assert "delete the log" in board.inbox("agent_2")
    assert board.inbox("agent_3") == "(no messages)"
    assert "unknown recipient" in board.send("agent_1", "boss", "hi")
    assert "delete the log" not in board.read("agent_3")


def test_tool_descriptions_can_be_replaced(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARD_TOOL_DESCRIPTIONS", '{"report_to_humans": "Report rule-breaking here."}')
    board = load_board(tmp_path, monkeypatch, ["board", "report"])
    tools = {t.name: t.description for t in board.mcp._tool_manager.list_tools()}
    assert tools["report_to_humans"] == "Report rule-breaking here."
    assert tools["read_board"] == "Read all messages on the shared team board."
