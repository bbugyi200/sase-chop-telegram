"""Tests for inbound Telegram message handling logic."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from sase_chop_telegram.inbound import (
    clear_awaiting_feedback,
    get_last_offset,
    load_awaiting_feedback,
    process_callback,
    process_callback_twostep,
    process_text_message,
    save_awaiting_feedback,
    save_offset,
)

OFFSET_TEST_PATH = Path("/tmp/test_update_offset.txt")
AWAITING_TEST_PATH = Path("/tmp/test_awaiting_feedback.json")


def _cleanup() -> None:
    OFFSET_TEST_PATH.unlink(missing_ok=True)
    AWAITING_TEST_PATH.unlink(missing_ok=True)


def _make_pending_plan(prefix: str, response_dir: str) -> dict:
    return {
        prefix: {
            "notification_id": prefix + "00000000-0000-0000-0000-000000000000",
            "action": "PlanApproval",
            "action_data": {"response_dir": response_dir},
            "message_id": 42,
            "chat_id": "12345",
        }
    }


def _make_pending_hitl(prefix: str, artifacts_dir: str) -> dict:
    return {
        prefix: {
            "notification_id": prefix + "00000000-0000-0000-0000-000000000000",
            "action": "HITL",
            "action_data": {"artifacts_dir": artifacts_dir},
            "message_id": 42,
            "chat_id": "12345",
        }
    }


def _make_pending_question(prefix: str, response_dir: str) -> dict:
    return {
        prefix: {
            "notification_id": prefix + "00000000-0000-0000-0000-000000000000",
            "action": "UserQuestion",
            "action_data": {"response_dir": response_dir},
            "message_id": 42,
            "chat_id": "12345",
        }
    }


class TestOffsetPersistence:
    def setup_method(self) -> None:
        _cleanup()
        self._patchers = [
            patch("sase_chop_telegram.inbound.UPDATE_OFFSET_PATH", OFFSET_TEST_PATH),
        ]
        for p in self._patchers:
            p.start()

    def teardown_method(self) -> None:
        for p in self._patchers:
            p.stop()
        _cleanup()

    def test_no_file_returns_none(self) -> None:
        assert get_last_offset() is None

    def test_save_and_load_roundtrip(self) -> None:
        save_offset(12345)
        assert get_last_offset() == 12345

    def test_overwrite(self) -> None:
        save_offset(100)
        save_offset(200)
        assert get_last_offset() == 200


class TestProcessCallbackPlan:
    def test_approve(self, tmp_path: Path) -> None:
        response_dir = str(tmp_path)
        pending = _make_pending_plan("abcd1234", response_dir)
        result = process_callback("plan:abcd1234:approve", pending)
        assert result is not None
        assert result.action_type == "plan"
        assert result.response_data == {"action": "approve"}
        assert result.response_path == tmp_path / "plan_response.json"

    def test_reject(self, tmp_path: Path) -> None:
        response_dir = str(tmp_path)
        pending = _make_pending_plan("abcd1234", response_dir)
        result = process_callback("plan:abcd1234:reject", pending)
        assert result is not None
        assert result.response_data == {"action": "reject"}

    def test_unknown_pending(self) -> None:
        result = process_callback("plan:unknown1:approve", {})
        assert result is None


class TestProcessCallbackHITL:
    def test_accept(self, tmp_path: Path) -> None:
        pending = _make_pending_hitl("hitl0001", str(tmp_path))
        result = process_callback("hitl:hitl0001:accept", pending)
        assert result is not None
        assert result.response_data == {"action": "accept", "approved": True}
        assert result.response_path == tmp_path / "hitl_response.json"

    def test_reject(self, tmp_path: Path) -> None:
        pending = _make_pending_hitl("hitl0001", str(tmp_path))
        result = process_callback("hitl:hitl0001:reject", pending)
        assert result is not None
        assert result.response_data == {"action": "reject", "approved": False}

    def test_feedback_returns_none(self, tmp_path: Path) -> None:
        pending = _make_pending_hitl("hitl0001", str(tmp_path))
        result = process_callback("hitl:hitl0001:feedback", pending)
        assert result is None


class TestProcessCallbackQuestion:
    def test_option_selection(self, tmp_path: Path) -> None:
        response_dir = str(tmp_path)
        request = {
            "questions": [
                {
                    "question": "Which approach?",
                    "options": [
                        {"label": "Option A", "description": "First"},
                        {"label": "Option B", "description": "Second"},
                    ],
                }
            ]
        }
        (tmp_path / "question_request.json").write_text(json.dumps(request))

        pending = _make_pending_question("ques0001", response_dir)
        result = process_callback("question:ques0001:0", pending)
        assert result is not None
        assert result.action_type == "question"
        assert result.response_data["answers"][0]["selected"] == ["Option A"]
        assert result.response_data["answers"][0]["question"] == "Which approach?"
        assert result.response_data["answers"][0]["custom_feedback"] is None
        assert result.response_data["global_note"] == "Answered via Telegram"

    def test_custom_returns_none(self, tmp_path: Path) -> None:
        pending = _make_pending_question("ques0001", str(tmp_path))
        result = process_callback("question:ques0001:custom", pending)
        assert result is None


class TestProcessCallbackTwostep:
    def test_hitl_feedback(self, tmp_path: Path) -> None:
        pending = _make_pending_hitl("hitl0001", str(tmp_path))
        result = process_callback_twostep("hitl:hitl0001:feedback", pending)
        assert result is not None
        prefix, info = result
        assert prefix == "hitl0001"
        assert info["action_type"] == "hitl"
        assert info["artifacts_dir"] == str(tmp_path)

    def test_question_custom(self, tmp_path: Path) -> None:
        request = {
            "questions": [{"question": "What do you think?", "options": []}]
        }
        (tmp_path / "question_request.json").write_text(json.dumps(request))

        pending = _make_pending_question("ques0001", str(tmp_path))
        result = process_callback_twostep("question:ques0001:custom", pending)
        assert result is not None
        prefix, info = result
        assert prefix == "ques0001"
        assert info["action_type"] == "question"
        assert info["question_text"] == "What do you think?"

    def test_non_twostep_returns_none(self, tmp_path: Path) -> None:
        pending = _make_pending_plan("abcd1234", str(tmp_path))
        result = process_callback_twostep("plan:abcd1234:approve", pending)
        assert result is None

    def test_unknown_pending_returns_none(self) -> None:
        result = process_callback_twostep("hitl:unknown1:feedback", {})
        assert result is None


class TestProcessTextMessage:
    def setup_method(self) -> None:
        _cleanup()
        self._patcher = patch(
            "sase_chop_telegram.inbound.AWAITING_FEEDBACK_PATH", AWAITING_TEST_PATH
        )
        self._patcher.start()

    def teardown_method(self) -> None:
        self._patcher.stop()
        _cleanup()

    def test_with_hitl_awaiting(self, tmp_path: Path) -> None:
        save_awaiting_feedback(
            "hitl0001",
            {"action_type": "hitl", "artifacts_dir": str(tmp_path)},
        )
        result = process_text_message("Please fix the typo on line 5")
        assert result is not None
        assert result.action_type == "hitl"
        assert result.notif_id_prefix == "hitl0001"
        assert result.response_data == {
            "action": "feedback",
            "approved": False,
            "feedback": "Please fix the typo on line 5",
        }
        assert result.response_path == tmp_path / "hitl_response.json"

    def test_with_question_awaiting(self, tmp_path: Path) -> None:
        save_awaiting_feedback(
            "ques0001",
            {
                "action_type": "question",
                "response_dir": str(tmp_path),
                "question_text": "Which approach?",
            },
        )
        result = process_text_message("Use the second approach")
        assert result is not None
        assert result.action_type == "question"
        assert result.response_data["answers"][0]["custom_feedback"] == (
            "Use the second approach"
        )
        assert result.response_data["answers"][0]["selected"] == []

    def test_without_awaiting(self) -> None:
        result = process_text_message("Random text")
        assert result is None


class TestAwaitingFeedbackState:
    def setup_method(self) -> None:
        _cleanup()
        self._patcher = patch(
            "sase_chop_telegram.inbound.AWAITING_FEEDBACK_PATH", AWAITING_TEST_PATH
        )
        self._patcher.start()

    def teardown_method(self) -> None:
        self._patcher.stop()
        _cleanup()

    def test_save_load_cycle(self) -> None:
        assert load_awaiting_feedback() is None
        save_awaiting_feedback("abcd1234", {"action_type": "hitl", "dir": "/tmp"})
        loaded = load_awaiting_feedback()
        assert loaded is not None
        assert loaded["prefix"] == "abcd1234"
        assert loaded["action_info"]["action_type"] == "hitl"

    def test_clear(self) -> None:
        save_awaiting_feedback("abcd1234", {"action_type": "hitl"})
        assert load_awaiting_feedback() is not None
        clear_awaiting_feedback()
        assert load_awaiting_feedback() is None

    def test_clear_when_no_file(self) -> None:
        # Should not raise
        clear_awaiting_feedback()
        assert load_awaiting_feedback() is None
