# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import xml.etree.ElementTree as ET  # noqa: N817
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Dict, List, Optional, Type, cast

from dataclasses_json import dataclass_json

from .subtest_aware_notifier import SubtestAwareNotifier
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


@dataclass_json()
@dataclass
class JUnitSchema(schema.Notifier):
    path: str = "lisa.junit.xml"

class _TestCaseXmlInfo:
    def __init__(self) -> None:
        self.xml: ET.Element

class _TestSuiteXmlInfo:
    def __init__(self) -> None:
        self.xml: ET.Element
        self.test_count: int = 0
        self.failed_count: int = 0

# Outputs tests results in JUnit format.
# See, https://llg.cubic.org/docs/junit/
class JUnit(SubtestAwareNotifier):
    @classmethod
    def type_name(cls) -> str:
        return "junit"

    @classmethod
    def type_schema(cls) -> Type[schema.TypedSchema]:
        return JUnitSchema

    def __init__(self, runbook: schema.TypedSchema) -> None:
        super().__init__(runbook=runbook)

        self._report_path: Path
        self._report_file: IO[Any]
        self._testsuites: ET.Element
        self._testsuites_xml_info: Dict[str, _TestSuiteXmlInfo]
        self._testcases_xml_info: Dict[str, _TestCaseXmlInfo]
        self._xml_tree: ET.ElementTree

    # Test runner is initializing.
    def _initialize(self, *args: Any, **kwargs: Any) -> None:
        runbook: JUnitSchema = cast(JUnitSchema, self.runbook)

        self._report_path = constants.RUN_LOCAL_LOG_PATH / runbook.path

        # Open file now, to avoid errors occuring after all the tests have completed.
        self._report_file = open(self._report_path, "wb")

        self._testsuites = ET.Element("testsuites")
        self._xml_tree = ET.ElementTree(self._testsuites)

        self._testsuites_xml_info = {}
        self._testcases_xml_info = {}

    # Test runner is closing.
    def finalize(self) -> None:
        try:
            self._write_results()

        finally:
            self._report_file.close()

        self._log.info(f"JUnit: {self._report_path}")

    def _write_results(self) -> None:
        self._report_file.truncate(0)
        self._report_file.seek(0)
        self._xml_tree.write(self._report_file, xml_declaration=True, encoding="utf-8")
        self._report_file.flush()

    def _create_or_get_testsuite_info(self, message: TestResultMessage) -> None:
        # Check if the test suite for this test case has been seen yet.
        if message.suite_full_name not in self._testsuites_xml_info:
            # Add test suite.
            testsuite_info = _TestSuiteXmlInfo()

            testsuite_info.xml = ET.SubElement(self._testsuites, "testsuite")
            testsuite_info.xml.attrib["name"] = message.suite_full_name

            # Timestamp must not contain timezone information.
            timestamp = message.time.replace(tzinfo=None).isoformat(timespec="seconds")
            testsuite_info.xml.attrib["timestamp"] = timestamp

            self._testsuites_xml_info[message.suite_full_name] = testsuite_info

        return self._testsuites_xml_info[message.suite_full_name]

    # TODO Declare this as NotImplemented in parent class
    def _set_test_case_info(self, message: TestResultMessage) -> None:
        case_full_name = f"{message.suite_full_name}.{message.name}"
        # Check if the test case has been seen yet.
        if case_full_name not in self._testcases_xml_info:
            # Add test suite.
            testcase_info = _TestCaseXmlInfo()

            # Get the testsuite element
            testsuite_info = self._create_or_get_testsuite_info(message)

            testcase_info.xml = ET.SubElement(testsuite_info.xml, "testcase")
            testcase_info.xml.attrib["name"] = message.name

            self._testcases_xml_info[case_full_name] = testcase_info

    # TODO Move these functions to parent class?
    # Test run started message.
    def _test_run_started(self, message: TestRunMessage) -> None:
        self._testsuites.attrib["name"] = message.runbook_name

    # TODO Move these functions to parent class?
    # Test run completed message.
    def _test_run_completed(self, message: TestRunMessage) -> None:
        total_tests = 0
        total_failures = 0

        for testsuite_info in self._testsuites_xml_info.values():
            testsuite_info.xml.attrib["tests"] = str(testsuite_info.test_count)
            testsuite_info.xml.attrib["failures"] = str(testsuite_info.failed_count)
            testsuite_info.xml.attrib["errors"] = "0"

            total_tests += testsuite_info.test_count
            total_failures += testsuite_info.failed_count

        self._testsuites.attrib["time"] = self._get_elapsed_str(message.elapsed)
        self._testsuites.attrib["tests"] = str(total_tests)
        self._testsuites.attrib["failures"] = str(total_failures)
        self._testsuites.attrib["errors"] = "0"

    # Add test case result to XML.
    def _add_test_case_result(
        self,
        message: TestResultMessage,
        suite_full_name: str,
        class_name: str,
        elapsed: float,
    ) -> None:
        testsuite_info = self._testsuites_xml_info.get(suite_full_name)
        if not testsuite_info:
            raise LisaException("Test suite not started.")

        case_full_name = f"{message.suite_full_name}.{message.name}"
        testcase_info = self._testcases_xml_info.get(case_full_name)
        if not testcase_info:
            raise LisaException(f"Test case {case_full_name} not started.")

        testcase = testcase_info.xml
        testcase.attrib["name"] = message.name
        testcase.attrib["classname"] = class_name
        testcase.attrib["time"] = self._get_elapsed_str(elapsed)

        self.add_failed_or_skipped(message, testcase)

        testsuite_info.test_count += 1

    # Add test case result to XML.
    def _add_subtest_case_result(
        self,
        message: SubTestMessage,
        suite_full_name: str,
        testcase_full_name: str,
        elapsed: float,
    ) -> None:
        testcase_info = self._testcases_xml_info.get(testcase_full_name)
        if not testcase_info:
            raise LisaException(f"Test case {testcase_full_name} not started.")

        subtestcase = ET.SubElement(testcase_info.xml, "subtestcase")
        subtestcase.attrib["name"] = message.name
        subtestcase.attrib["testcase"] = testcase_full_name
        subtestcase.attrib["time"] = self._get_elapsed_str(elapsed)

        self.add_failed_or_skipped(message, subtestcase)

    def add_failed_or_skipped(self, message: TestResultMessageBase, xml: ET.SubElement):
        if message.status == TestStatus.FAILED:
            failure = ET.SubElement(xml, "failure")
            failure.attrib["message"] = message.message
            failure.text = message.stacktrace

        elif (
            message.status == TestStatus.SKIPPED
            or message.status == TestStatus.ATTEMPTED
        ):
            skipped = ET.SubElement(xml, "skipped")
            skipped.attrib["message"] = message.message

    def _get_elapsed_str(self, elapsed: float) -> str:
        return f"{elapsed:.3f}"
