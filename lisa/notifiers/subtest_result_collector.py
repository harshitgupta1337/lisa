from assertpy import assert_that
from typing import Any, Dict, Type

from lisa import schema
from lisa.messages import SubTestMessage, TestResultMessage, TestResultMessageBase, TestRunMessage, TestStatus
from lisa.util import LisaException
from lisa.util.logger import get_logger
from .subtest_aware_notifier import SubtestAwareNotifier

class SubTestResultCollector(SubtestAwareNotifier):
    @classmethod
    def type_name(cls) -> str:
        return "subtestresultcollector"

    @classmethod
    def type_schema(cls) -> Type[schema.TypedSchema]:
        return schema.Notifier

    def __init__(self, runbook: schema.TypedSchema) -> None:
        super().__init__(runbook=runbook)
        self._log = get_logger("notifier", self.__class__.__name__)
        self._test_cases: Dict[str, Dict[str, bool]]

    def _initialize(self, *args: Any, **kwargs: Any) -> None:
        self._test_cases = {}

    def finalize(self) -> None:
        self._log.info("________________________________________")
        self._log.info("SubTest Case Results")
        for test_case in self._test_cases:
            subtest_results = self._test_cases[test_case]
            if len(subtest_results) == 0:
                # Not printing tests that do not have any subtest cases.
                continue
            self._log.info(f"{test_case}")
            for subtest in subtest_results:
                self._log.info(f"|--- {subtest}:\t{subtest_results[subtest]}")

    def _test_run_started(self, message: TestRunMessage) -> None:
        pass

    def _test_run_completed(self, message: TestRunMessage) -> None:
        pass

    def _init_test_case_info(self, message: TestResultMessage) -> None:
        case_full_name = f"{message.suite_full_name}.{message.name}"
        if case_full_name not in self._test_cases:
            self._test_cases[case_full_name] = {}

    # Add test case result to XML.
    def _add_test_case_result(
        self,
        message: TestResultMessageBase,
        suite_full_name: str,
        class_name: str,
        elapsed: float,
    ) -> None:
        pass

    # Add subtest case result to XML.
    def _add_subtest_case_result(
        self,
        message: SubTestMessage,
        suite_full_name: str,
        testcase_full_name: str,
        elapsed: float,
    ) -> None:
        assert isinstance(message, SubTestMessage), f"actual: {type(message)}"

        testcase_info = self._test_cases.get(testcase_full_name)
        if testcase_info == None:
            raise LisaException(f"Test case {testcase_full_name} not started.")

        if message.status == TestStatus.PASSED:
            testcase_info[message.name] = "PASSED"
        elif message.status == TestStatus.FAILED:
            testcase_info[message.name] = "FAILED"
        elif message.status == TestStatus.SKIPPED or message.status == TestStatus.ATTEMPTED:
            testcase_info[message.name] = "SKIPPED"
