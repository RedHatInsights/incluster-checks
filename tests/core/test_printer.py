"""
Tests for StructedPrinter (JSON and JUnit XML formatter).
"""

import json
import os
import stat
import tempfile
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path

import pytest

from in_cluster_checks.core.printer import StructedPrinter
from in_cluster_checks.utils.enums import Status


def _make_report(domain, key, status, component=None, details=None):
    if component is None:
        component = f"in_cluster_checks.{domain}.{key}"
    if details is None:
        details = [
            {
                "node_ip": "192.168.1.10",
                "node_name": "node1",
                "status": status,
                "bash_cmd_lines": [],
                "rule_log": [],
                "timestamp": "2026-01-18 10:00:00",
            }
        ]
    return {
        "rule_id": f"{domain}|{key}",
        "component": component,
        "key": key,
        "status": status,
        "description": f"Test {key}",
        "domain": domain,
        "details": details,
    }


class TestStructedPrinter:
    """Test StructedPrinter JSON formatting."""

    def test_print_to_json_creates_file(self, tmp_path):
        """Test that print_to_json creates a JSON file with restricted permissions."""
        output_file = tmp_path / "test_output.json"

        test_data = {
            "system": {"metadata": {"cluster_id": "test-123"}},
            "reports": []
        }

        StructedPrinter.print_to_json(test_data, str(output_file))

        assert output_file.exists()
        with open(output_file) as f:
            loaded_data = json.load(f)

        assert loaded_data == test_data

        file_mode = stat.S_IMODE(os.stat(output_file).st_mode)
        assert file_mode == 0o600

    def test_print_to_json_overwrites_existing_file(self, tmp_path):
        """Test that print_to_json overwrites an existing file and sets restricted permissions."""
        output_file = tmp_path / "test_output.json"
        output_file.write_text('{"old": "data"}')
        os.chmod(output_file, 0o644)

        new_data = {"new": "data"}
        StructedPrinter.print_to_json(new_data, str(output_file))

        with open(output_file) as f:
            loaded_data = json.load(f)
        assert loaded_data == new_data

        file_mode = stat.S_IMODE(os.stat(output_file).st_mode)
        assert file_mode == 0o600

    def test_format_results_insights_format(self):
        """Test that format_results produces Insights-compatible format with grouped hosts."""
        # Sample flow result with single host
        flow_results = [
            {
                'domain_name': 'network_validations',
                'details': OrderedDict({
                    'node1 - 192.168.1.10': OrderedDict({
                        'test_validator': {
                            'node_ip': '192.168.1.10',
                            'node_name': 'node1',
                            'description_title': 'Test Rule',
                            'status': Status.PASSED.value,
                            'bash_cmd_lines': ['test command'],
                            'rule_log': [],
                            'describe_msg': '',
                            'time': '2026-01-18 10:00:00'
                        }
                    })
                })
            }
        ]

        validator_component_map = {
            'test_validator': 'in_cluster_checks.rules.test.TestValidator'
        }

        result = StructedPrinter.format_results(
            flow_results,
            validator_component_map
        )

        # Verify structure - result is a list of reports
        assert isinstance(result, list)

        # Verify reports - one entry per validation
        assert len(result) == 1
        report = result[0]

        assert report['rule_id'] == 'network_validations|test_validator'
        assert report['component'] == 'in_cluster_checks.rules.test.TestValidator'
        assert report['key'] == 'test_validator'
        assert report['status'] == Status.PASSED.value  # Aggregated status
        assert report['description'] == 'Test Rule'
        assert report['domain'] == 'network_validations'

        # Verify details is now an array
        assert isinstance(report['details'], list)
        assert len(report['details']) == 1

        # Check first host result
        host_result = report['details'][0]
        assert host_result['node_ip'] == '192.168.1.10'
        assert host_result['node_name'] == 'node1'
        assert host_result['status'] == Status.PASSED.value
        assert host_result['bash_cmd_lines'] == ['test command']
        assert host_result['rule_log'] == []
        assert host_result['timestamp'] == '2026-01-18 10:00:00'

    def test_format_results_multiple_validators(self):
        """Test format_results with multiple validators (passed and failed)."""
        flow_results = [
            {
                'domain_name': 'network_validations',
                'details': OrderedDict({
                    'node1 - 192.168.1.10': OrderedDict({
                        'validator1': {
                            'node_ip': '192.168.1.10',
                            'node_name': 'node1',
                            'description_title': 'Rule 1',
                            'status': Status.PASSED.value,
                            'bash_cmd_lines': [],
                            'rule_log': [],
                            'describe_msg': '',
                            'time': '2026-01-18 10:00:00'
                        },
                        'validator2': {
                            'node_ip': '192.168.1.10',
                            'node_name': 'node1',
                            'description_title': 'Rule 2',
                            'status': Status.FAILED.value,
                            'bash_cmd_lines': [],
                            'rule_log': [],
                            'describe_msg': 'Validation failed',
                            'time': '2026-01-18 10:00:01'
                        }
                    })
                })
            }
        ]

        result = StructedPrinter.format_results(
            flow_results,
            {}
        )

        # Two validators = two report entries
        assert len(result) == 2

        # Check passing validator
        pass_report = result[0]
        assert pass_report['status'] == Status.PASSED.value
        assert pass_report['description'] == 'Rule 1'
        assert isinstance(pass_report['details'], list)
        assert len(pass_report['details']) == 1

        # Check failing validator
        fail_report = result[1]
        assert fail_report['status'] == Status.FAILED.value
        assert fail_report['description'] == 'Rule 2'
        assert isinstance(fail_report['details'], list)
        assert len(fail_report['details']) == 1
        assert fail_report['details'][0]['message'] == 'Validation failed'

    def test_format_results_with_system_info(self):
        """Test that system_info is included when present."""
        flow_results = [
            {
                'domain_name': 'network_validations',
                'details': OrderedDict({
                    'node1 - 192.168.1.10': OrderedDict({
                        'test_informator': {
                            'node_ip': '192.168.1.10',
                            'node_name': 'node1',
                            'description_title': 'Test Informator',
                            'status': Status.INFO.value,
                            'bash_cmd_lines': [],
                            'rule_log': [],
                            'describe_msg': '',
                            'time': '2026-01-18 10:00:00',
                            'system_info': {
                                'cpu_count': 4,
                                'memory_gb': 16
                            }
                        }
                    })
                })
            }
        ]

        result = StructedPrinter.format_results(
            flow_results,
            {}
        )

        # system_info should be in first host's details
        host_result = result[0]['details'][0]
        assert 'system_info' in host_result
        assert host_result['system_info'] == {
            'cpu_count': 4,
            'memory_gb': 16
        }

    def test_format_results_fallback_component_name(self):
        """Test that component name falls back to default if not in map."""
        flow_results = [
            {
                'domain_name': 'network_validations',
                'details': OrderedDict({
                    'node1 - 192.168.1.10': OrderedDict({
                        'unknown_validator': {
                            'node_ip': '192.168.1.10',
                            'node_name': 'node1',
                            'description_title': 'Unknown',
                            'status': Status.PASSED.value,
                            'bash_cmd_lines': [],
                            'rule_log': [],
                            'describe_msg': '',
                            'time': '2026-01-18 10:00:00'
                        }
                    })
                })
            }
        ]

        result = StructedPrinter.format_results(
            flow_results,
            {}  # Empty component map
        )

        # Should use fallback format
        assert result[0]['component'] == 'in_cluster_checks.network_validations.unknown_validator'

    def test_format_results_multi_node_with_aggregation(self):
        """Test format_results with multiple nodes - validates grouping and status aggregation."""
        flow_results = [
            {
                'domain_name': 'network',
                'details': OrderedDict({
                    'master-0 - 192.168.1.10': OrderedDict({
                        'ovs_check': {
                            'node_ip': '192.168.1.10',
                            'node_name': 'master-0',
                            'description_title': 'OVS Interface Check',
                            'status': Status.PASSED.value,
                            'bash_cmd_lines': ['ovs-vsctl show'],
                            'rule_log': ['Port bond0 is UP'],
                            'describe_msg': '',
                            'time': '2026-01-25 14:30:00'
                        }
                    }),
                    'master-1 - 192.168.1.11': OrderedDict({
                        'ovs_check': {
                            'node_ip': '192.168.1.11',
                            'node_name': 'master-1',
                            'description_title': 'OVS Interface Check',
                            'status': Status.FAILED.value,
                            'bash_cmd_lines': ['ovs-vsctl show'],
                            'rule_log': ['ERROR: Port bond0 not found'],
                            'describe_msg': 'Port bond0 is missing',
                            'time': '2026-01-25 14:30:01'
                        }
                    }),
                    'worker-0 - 192.168.1.20': OrderedDict({
                        'ovs_check': {
                            'node_ip': '192.168.1.20',
                            'node_name': 'worker-0',
                            'description_title': 'OVS Interface Check',
                            'status': Status.PASSED.value,
                            'bash_cmd_lines': ['ovs-vsctl show'],
                            'rule_log': ['Port bond0 is UP'],
                            'describe_msg': '',
                            'time': '2026-01-25 14:30:02'
                        }
                    })
                })
            }
        ]

        result = StructedPrinter.format_results(
            flow_results,
            {}
        )

        # Should have 1 report (one validation across 3 hosts)
        assert len(result) == 1
        report = result[0]

        # Aggregated status should be 'failed' (worst status wins)
        assert report['status'] == Status.FAILED.value
        assert report['key'] == 'ovs_check'
        assert report['description'] == 'OVS Interface Check'

        # Should have 3 host results in details array
        assert isinstance(report['details'], list)
        assert len(report['details']) == 3

        # Verify each host result
        host1 = report['details'][0]
        assert host1['node_ip'] == '192.168.1.10'
        assert host1['node_name'] == 'master-0'
        assert host1['status'] == Status.PASSED.value
        assert 'message' not in host1

        host2 = report['details'][1]
        assert host2['node_ip'] == '192.168.1.11'
        assert host2['node_name'] == 'master-1'
        assert host2['status'] == Status.FAILED.value
        assert host2['message'] == 'Port bond0 is missing'

        host3 = report['details'][2]
        assert host3['node_ip'] == '192.168.1.20'
        assert host3['node_name'] == 'worker-0'
        assert host3['status'] == Status.PASSED.value

    def test_format_results_status_aggregation_priority(self):
        """Test that status aggregation follows correct priority: failed > warning > info > passed."""
        flow_results = [
            {
                'domain_name': 'test',
                'details': OrderedDict({
                    'node1 - 192.168.1.1': OrderedDict({
                        'test_val': {
                            'node_ip': '192.168.1.1',
                            'node_name': 'node1',
                            'description_title': 'Test',
                            'status': Status.PASSED.value,
                            'bash_cmd_lines': [],
                            'rule_log': [],
                            'time': '2026-01-25 14:30:00'
                        }
                    }),
                    'node2 - 192.168.1.2': OrderedDict({
                        'test_val': {
                            'node_ip': '192.168.1.2',
                            'node_name': 'node2',
                            'description_title': 'Test',
                            'status': Status.WARNING.value,
                            'bash_cmd_lines': [],
                            'rule_log': [],
                            'time': '2026-01-25 14:30:01'
                        }
                    }),
                    'node3 - 192.168.1.3': OrderedDict({
                        'test_val': {
                            'node_ip': '192.168.1.3',
                            'node_name': 'node3',
                            'description_title': 'Test',
                            'status': Status.PASSED.value,
                            'bash_cmd_lines': [],
                            'rule_log': [],
                            'time': '2026-01-25 14:30:02'
                        }
                    })
                })
            }
        ]

        result = StructedPrinter.format_results(
            flow_results,
            {}
        )

        # Aggregated status should be 'warning' (worst among passed/warning)
        assert result[0]['status'] == Status.WARNING.value
        assert len(result[0]['details']) == 3


class TestJUnitOutput:
    """Test JUnit XML output formatting."""

    def test_print_to_junit_creates_valid_xml(self, tmp_path):
        output_file = tmp_path / "results.xml"
        reports = [_make_report("hw", "check_disk", Status.PASSED.value)]

        StructedPrinter.print_to_junit(reports, str(output_file))

        assert output_file.exists()
        tree = ET.parse(output_file)
        root = tree.getroot()
        assert root.tag == "testsuites"

        suites = root.findall("testsuite")
        assert len(suites) == 1
        assert suites[0].get("name") == "hw"

        cases = suites[0].findall("testcase")
        assert len(cases) == 1
        assert cases[0].get("name") == "check_disk [node1]"
        assert cases[0].get("classname") == "in_cluster_checks.hw.check_disk"

        assert cases[0].find("failure") is None
        assert cases[0].find("skipped") is None

    def test_print_to_junit_failed_status(self, tmp_path):
        output_file = tmp_path / "results.xml"
        details = [
            {
                "node_ip": "192.168.1.10",
                "node_name": "node1",
                "status": Status.FAILED.value,
                "message": "Disk usage at 98%",
                "bash_cmd_lines": [],
                "rule_log": [],
                "timestamp": "2026-01-18 10:00:00",
            }
        ]
        reports = [_make_report("hw", "check_disk", Status.FAILED.value, details=details)]

        StructedPrinter.print_to_junit(reports, str(output_file))

        tree = ET.parse(output_file)
        case = tree.getroot().find(".//testcase")
        failure = case.find("failure")
        assert failure is not None
        assert failure.get("message") == "Disk usage at 98%"
        assert failure.get("type") == "failure"

    def test_print_to_junit_warning_status(self, tmp_path):
        output_file = tmp_path / "results.xml"
        details = [
            {
                "node_ip": "192.168.1.10",
                "node_name": "node1",
                "status": Status.WARNING.value,
                "message": "Disk usage at 80%",
                "bash_cmd_lines": [],
                "rule_log": [],
                "timestamp": "2026-01-18 10:00:00",
            }
        ]
        reports = [_make_report("hw", "check_disk", Status.WARNING.value, details=details)]

        StructedPrinter.print_to_junit(reports, str(output_file))

        tree = ET.parse(output_file)
        case = tree.getroot().find(".//testcase")
        failure = case.find("failure")
        assert failure is not None
        assert failure.get("message") == "Disk usage at 80%"
        assert failure.get("type") == "warning"

    def test_print_to_junit_skip_status(self, tmp_path):
        output_file = tmp_path / "results.xml"
        details = [
            {
                "node_ip": "192.168.1.10",
                "node_name": "node1",
                "status": Status.SKIP.value,
                "message": "Command timed out",
                "bash_cmd_lines": [],
                "rule_log": [],
                "timestamp": "2026-01-18 10:00:00",
            }
        ]
        reports = [_make_report("hw", "check_disk", Status.SKIP.value, details=details)]

        StructedPrinter.print_to_junit(reports, str(output_file))

        tree = ET.parse(output_file)
        case = tree.getroot().find(".//testcase")
        skipped = case.find("skipped")
        assert skipped is not None
        assert skipped.get("message") == "Command timed out"
        assert case.find("failure") is None

    def test_print_to_junit_not_applicable_status(self, tmp_path):
        output_file = tmp_path / "results.xml"
        details = [
            {
                "node_ip": "192.168.1.10",
                "node_name": "node1",
                "status": Status.NOT_APPLICABLE.value,
                "message": "Prerequisite not met",
                "bash_cmd_lines": [],
                "rule_log": [],
                "timestamp": "2026-01-18 10:00:00",
            }
        ]
        reports = [_make_report("hw", "check_disk", Status.NOT_APPLICABLE.value, details=details)]

        StructedPrinter.print_to_junit(reports, str(output_file))

        tree = ET.parse(output_file)
        case = tree.getroot().find(".//testcase")
        skipped = case.find("skipped")
        assert skipped is not None
        assert skipped.get("message") == "Prerequisite not met"

    def test_print_to_junit_info_status(self, tmp_path):
        output_file = tmp_path / "results.xml"
        reports = [_make_report("hw", "sys_info", Status.INFO.value)]

        StructedPrinter.print_to_junit(reports, str(output_file))

        tree = ET.parse(output_file)
        case = tree.getroot().find(".//testcase")
        assert case.find("failure") is None
        assert case.find("skipped") is None

    def test_print_to_junit_multi_host(self, tmp_path):
        output_file = tmp_path / "results.xml"
        details = [
            {
                "node_ip": "192.168.1.10",
                "node_name": "master-0",
                "status": Status.PASSED.value,
                "bash_cmd_lines": [],
                "rule_log": [],
                "timestamp": "2026-01-25 14:30:00",
            },
            {
                "node_ip": "192.168.1.11",
                "node_name": "master-1",
                "status": Status.FAILED.value,
                "message": "Port bond0 is missing",
                "bash_cmd_lines": [],
                "rule_log": [],
                "timestamp": "2026-01-25 14:30:01",
            },
            {
                "node_ip": "192.168.1.20",
                "node_name": "worker-0",
                "status": Status.PASSED.value,
                "bash_cmd_lines": [],
                "rule_log": [],
                "timestamp": "2026-01-25 14:30:02",
            },
        ]
        reports = [_make_report("network", "ovs_check", Status.FAILED.value, details=details)]

        StructedPrinter.print_to_junit(reports, str(output_file))

        tree = ET.parse(output_file)
        suite = tree.getroot().find("testsuite")
        assert suite.get("tests") == "3"
        assert suite.get("failures") == "1"

        cases = suite.findall("testcase")
        assert len(cases) == 3
        assert cases[0].get("name") == "ovs_check [master-0]"
        assert cases[0].find("failure") is None
        assert cases[1].get("name") == "ovs_check [master-1]"
        assert cases[1].find("failure") is not None
        assert cases[2].get("name") == "ovs_check [worker-0]"
        assert cases[2].find("failure") is None

    def test_print_to_junit_multi_domain(self, tmp_path):
        output_file = tmp_path / "results.xml"
        reports = [
            _make_report("hw", "check_disk", Status.PASSED.value),
            _make_report("network", "ovs_check", Status.PASSED.value),
        ]

        StructedPrinter.print_to_junit(reports, str(output_file))

        tree = ET.parse(output_file)
        suites = tree.getroot().findall("testsuite")
        assert len(suites) == 2
        suite_names = {s.get("name") for s in suites}
        assert suite_names == {"hw", "network"}

    def test_print_to_junit_rule_log_in_system_out(self, tmp_path):
        output_file = tmp_path / "results.xml"
        details = [
            {
                "node_ip": "192.168.1.10",
                "node_name": "node1",
                "status": Status.PASSED.value,
                "bash_cmd_lines": [],
                "rule_log": ["line 1", "line 2", "line 3"],
                "timestamp": "2026-01-18 10:00:00",
            }
        ]
        reports = [_make_report("hw", "check_disk", Status.PASSED.value, details=details)]

        StructedPrinter.print_to_junit(reports, str(output_file))

        tree = ET.parse(output_file)
        case = tree.getroot().find(".//testcase")
        system_out = case.find("system-out")
        assert system_out is not None
        assert "line 1" in system_out.text
        assert "line 2" in system_out.text
        assert "line 3" in system_out.text

    def test_print_to_junit_testcase_time(self, tmp_path):
        output_file = tmp_path / "results.xml"
        details = [
            {
                "node_ip": "192.168.1.10",
                "node_name": "node1",
                "status": Status.PASSED.value,
                "bash_cmd_lines": [],
                "rule_log": [],
                "run_time": 2.5,
                "timestamp": "2026-01-18 10:00:00",
            }
        ]
        reports = [_make_report("hw", "check_disk", Status.PASSED.value, details=details)]

        StructedPrinter.print_to_junit(reports, str(output_file))

        tree = ET.parse(output_file)
        case = tree.getroot().find(".//testcase")
        assert case.get("time") == "2.5"

    def test_print_to_junit_strips_illegal_xml_chars(self, tmp_path):
        output_file = tmp_path / "results.xml"
        details = [
            {
                "node_ip": "192.168.1.10",
                "node_name": "node1",
                "status": Status.FAILED.value,
                "message": "bad\x00output\x07here",
                "bash_cmd_lines": [],
                "rule_log": ["line\x01one", "line\x1ftwo"],
                "timestamp": "2026-01-18 10:00:00",
            }
        ]
        reports = [_make_report("hw", "check_disk", Status.FAILED.value, details=details)]

        StructedPrinter.print_to_junit(reports, str(output_file))

        tree = ET.parse(output_file)
        case = tree.getroot().find(".//testcase")
        failure = case.find("failure")
        assert failure.get("message") == "badoutputhere"
        system_out = case.find("system-out")
        assert "\x01" not in system_out.text
        assert "\x1f" not in system_out.text
        assert "lineone" in system_out.text
        assert "linetwo" in system_out.text

    def test_print_to_junit_strips_illegal_chars_from_attributes(self, tmp_path):
        """Verify that domain, node_name, key, and component are sanitized."""
        output_file = tmp_path / "results.xml"
        details = [
            {
                "node_ip": "192.168.1.10",
                "node_name": "node\x00one",
                "status": Status.PASSED.value,
                "message": "",
                "bash_cmd_lines": [],
                "rule_log": [],
                "timestamp": "2026-01-18 10:00:00",
            }
        ]
        reports = [
            {
                "rule_id": "hw\x07bad|check\x01disk",
                "component": "in_cluster\x0b.hw.check_disk",
                "key": "check\x03disk",
                "status": Status.PASSED.value,
                "description": "Test",
                "domain": "h\x08w",
                "details": details,
            }
        ]

        StructedPrinter.print_to_junit(reports, str(output_file))

        tree = ET.parse(output_file)
        suite = tree.getroot().find("testsuite")
        assert suite.get("name") == "hw"

        case = suite.find("testcase")
        assert case.get("name") == "checkdisk [nodeone]"
        assert case.get("classname") == "in_cluster.hw.check_disk"

    def test_print_to_junit_empty_results(self, tmp_path):
        output_file = tmp_path / "results.xml"

        StructedPrinter.print_to_junit([], str(output_file))

        assert output_file.exists()
        tree = ET.parse(output_file)
        root = tree.getroot()
        assert root.tag == "testsuites"
        assert root.findall("testsuite") == []
