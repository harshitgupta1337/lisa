from assertpy import assert_that
from typing import Any, Dict, Type

from lisa import schema
from lisa.messages import SubTestMessage, TestResultMessage, TestResultMessageBase, TestRunMessage, TestStatus
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
        self.subtest_passed: Dict[str, bool]

    def _initialize(self, *args: Any, **kwargs: Any) -> None:
        self.subtest_passed = {}

    # TODO Finish implementing this function
    def finalize(self) -> None:
        for subtest in self.subtest_passed:
            result = self.subtest_passed[subtest]
            # TODO get_logger from lisa.util.logger. See how its used in notifier.py
            print (f"{subtest}\t{result}")

    def _test_run_started(self, message: TestRunMessage) -> None:
        pass

    def _test_run_completed(self, message: TestRunMessage) -> None:
        pass

    def _set_test_case_info(self, message: TestResultMessage) -> None:
        pass

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
        class_name: str,
        elapsed: float,
    ) -> None:
        assert isinstance(message, SubTestMessage), f"actual: {type(message)}"

        assert_that(message.status).is_in(TestStatus.RUNNING, TestStatus.PASSED)

        if message.status == TestStatus.RUNNING:
            self.subtest_passed[message.name] = False
        else:
            self.subtest_passed[message.name] = True



