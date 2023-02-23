# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Dict, List, Optional, Type, cast

from dataclasses_json import dataclass_json

from lisa import schema
from lisa.messages import (
    MessageBase,
    SubTestMessage,
    TestResultMessage,
    TestResultMessageBase,
    TestRunMessage,
    TestRunStatus,
    TestStatus,
)
from lisa.notifier import Notifier
from lisa.util import LisaException, constants

# TODO IF these Info classes are not used by any other file, then add leading underscore to their names
# TODO Check which fields are not required
class TestCaseRuntimeInfo:
    def __init__(self) -> None:
        self.suite_full_name: str = ""
        self.name: str = ""
        self.active_subtest_name: Optional[str] = None
        self.last_seen_timestamp: float = 0.0
        self.subtest_total_elapsed: float = 0.0

class SubtestAwareNotifier(Notifier):
    @classmethod
    def type_name(cls) -> str:
        # no type_name, not able to import from yaml book.
        return ""

    def __init__(self, runbook: schema.TypedSchema) -> None:
        super().__init__(runbook=runbook)

        self._testcases_info: Dict[str, TestCaseRuntimeInfo] = {}

    # The types of messages that this class supports.
    def _subscribed_message_type(self) -> List[Type[MessageBase]]:
        return [TestResultMessage, TestRunMessage, SubTestMessage]

    # Handle a message.
    def _received_message(self, message: MessageBase) -> None:
        if isinstance(message, TestRunMessage):
            self._received_test_run(message)

        elif isinstance(message, TestResultMessage):
            self._received_test_result(message)

        elif isinstance(message, SubTestMessage):
            self._received_sub_test(message)

    # Handle a test run message.
    def _received_test_run(self, message: TestRunMessage) -> None:
        if message.status == TestRunStatus.INITIALIZING:
            self._test_run_started(message)

        elif (
            message.status == TestRunStatus.FAILED
            or message.status == TestRunStatus.SUCCESS
        ):
            self._test_run_completed(message)

    # Handle a test case message.
    def _received_test_result(self, message: TestResultMessage) -> None:
        if message.status in [TestStatus.RUNNING, TestStatus.SKIPPED]:
            self._test_case_running(message)

        if message.is_completed:
            self._test_case_completed(message)

    # Handle a sub test case message.
    def _received_sub_test(self, message: SubTestMessage) -> None:
        if message.status == TestStatus.RUNNING:
            self._sub_test_case_running(message)

        elif message.is_completed:
            self._sub_test_case_completed(message)

    # Sub test case started message.
    def _sub_test_case_running(self, message: SubTestMessage) -> None:
        testcase_info = self._testcases_info[message.id_]

        # Check if there is an already active sub-test case that wasn't closed out.
        if testcase_info.active_subtest_name is not None:
            # Assume the previous sub-test case succeeded.
            completed_message = SubTestMessage()
            completed_message.id_ = message.id_
            completed_message.name = testcase_info.active_subtest_name
            completed_message.status = TestStatus.PASSED
            completed_message.elapsed = message.elapsed

            self._sub_test_case_completed(completed_message)

        # Mark the new sub-test case as running.
        testcase_info.active_subtest_name = message.name
        testcase_info.last_seen_timestamp = message.elapsed

    # Sub test case completed message.
    def _sub_test_case_completed(self, message: SubTestMessage) -> None:
        testcase_info = self._testcases_info[message.id_]

        # Check if there is an already active sub-test.
        if testcase_info.active_subtest_name is not None:
            if testcase_info.active_subtest_name != message.name:
                # The active sub-test is not the same as the one that just completed.
                # Report the problem.
                raise LisaException(
                    "Completed sub-test is not the same as the active sub-test."
                )

            testcase_info.active_subtest_name = None

        # Calculate the amount of time spent in the sub-test case.
        elapsed = message.elapsed - testcase_info.last_seen_timestamp
        testcase_info.subtest_total_elapsed += elapsed

        # Add sub-test case result.
        self._add_subtest_case_result(
            message,
            testcase_info.suite_full_name,
            f"{testcase_info.suite_full_name}.{testcase_info.name}",
            elapsed,
        )

        testcase_info.last_seen_timestamp = message.elapsed

    # Test case started message.
    def _test_case_running(self, message: TestResultMessage) -> None:
        self._init_test_case_info(message)

        # Initialize test-case info.
        self._set_test_case_runtime_info(message)

    # Test case completed message.
    def _test_case_completed(self, message: TestResultMessage) -> None:
        self._init_test_case_info(message)

        # check if the message id is in the testcases_info dictionary
        # if not, then it is a test case  was attached to a failed environment
        # and we should add it to the results
        if message.id_ not in self._testcases_info.keys():
            self._set_test_case_runtime_info(message)

        testcase_info = self._testcases_info[message.id_]

        # Check if there is an already active sub-test case that wasn't closed out.
        if testcase_info.active_subtest_name is not None:
            # Close out the sub-test case.
            # If the test case encountered any errors, assume they are associated with
            # the active sub-test case.
            completed_message = SubTestMessage()
            completed_message.id_ = message.id_
            completed_message.name = testcase_info.active_subtest_name
            completed_message.status = message.status
            completed_message.message = message.message
            completed_message.stacktrace = message.stacktrace
            completed_message.elapsed = message.elapsed

            self._sub_test_case_completed(completed_message)

        # Calculate total time spent in test case that was not spent in a sub-test case.
        elapsed = message.elapsed - testcase_info.subtest_total_elapsed

        # Add test case result.
        self._add_test_case_result(
            message, message.suite_full_name, message.suite_full_name, elapsed
        )

    def _set_test_case_runtime_info(self, message: TestResultMessage) -> None:
        testcase_info = TestCaseRuntimeInfo()
        testcase_info.suite_full_name = message.suite_full_name
        testcase_info.name = message.name
        testcase_info.last_seen_timestamp = message.elapsed
        self._testcases_info[message.id_] = testcase_info

    # Test runner is closing.
    def finalize(self) -> None:
        pass

    # Alert the notifier about the start of a Test Run.
    # Use this event to update metadata about the Test Run.
    def _test_run_started(self, message: TestRunMessage) -> None:
        raise NotImplementedError

    # Alert the notifier about the end of a Test Run.
    # Use this event to update metadata about the Test Run.
    def _test_run_completed(self, message: TestRunMessage) -> None:
        raise NotImplementedError

    # Initialize metadata about a Test Case.
    # This function is called when Test Case starts and completes.
    # Ensure that its implementation is idempotent.
    def _init_test_case_info(self, message: TestResultMessage) -> None:
        raise NotImplementedError

    # Add the result of a Test Case.
    def _add_test_case_result(
        self,
        message: TestResultMessageBase,
        suite_full_name: str,
        class_name: str,
        elapsed: float,
    ) -> None:
        raise NotImplementedError    

    # Add the result of a SubTest Case.
    def _add_subtest_case_result(
        self,
        message: SubTestMessage,
        suite_full_name: str,
        testcase_full_name: str,
        elapsed: float,
    ) -> None:
        raise NotImplementedError
