"""Published client history copy must match hydracept_contracts.job_history."""

from __future__ import annotations

from hydracept.history import (
    HOW_TO_READ_EXECUTED_PROMPT,
    JOB_INSPECT_DESCRIPTION,
    JOBS_FIND_DESCRIPTION,
    executed_prompt_text,
    history_find_result,
    inspect_job_bundle,
)
from hydracept_contracts.job_history import (
    HOW_TO_READ_EXECUTED_PROMPT as CONTRACT_HINT,
    JOB_INSPECT_DESCRIPTION as CONTRACT_INSPECT,
    JOBS_FIND_DESCRIPTION as CONTRACT_FIND,
    executed_prompt_text as contract_executed_prompt_text,
    history_find_result as contract_history_find_result,
    inspect_job_bundle as contract_inspect_job_bundle,
)


def test_agent_facing_history_copy_matches_contracts() -> None:
    assert JOBS_FIND_DESCRIPTION == CONTRACT_FIND
    assert JOB_INSPECT_DESCRIPTION == CONTRACT_INSPECT
    assert HOW_TO_READ_EXECUTED_PROMPT == CONTRACT_HINT


def test_inspect_bundle_matches_contracts() -> None:
    job = {
        "jobId": "fex_1",
        "capabilityKey": "text.general.fast.v1",
        "status": "succeeded",
        "requestSnapshot": {"input": {"prompt": "Finish chapter 1"}},
    }
    assert executed_prompt_text(job) == contract_executed_prompt_text(job) == "Finish chapter 1"
    messages_job = {
        "requestSnapshot": {
            "input": {"messages": [{"role": "user", "content": "Finish chapter 1"}]}
        }
    }
    assert (
        executed_prompt_text(messages_job)
        == contract_executed_prompt_text(messages_job)
        == "Finish chapter 1"
    )
    assert inspect_job_bundle(job) == contract_inspect_job_bundle(job)
    listed = history_find_result({"items": [{"jobId": "fex_1"}]})
    assert listed == contract_history_find_result({"items": [{"jobId": "fex_1"}]})
    assert "executedPrompt" in listed["howToReadExecutedPrompt"]
