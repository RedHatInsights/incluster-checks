"""
Tests for StructedPrinter (JSON formatter).
"""

import json
import tempfile
from collections import OrderedDict
from pathlib import Path

import pytest

from in_cluster_checks.core.printer import StructedPrinter
from in_cluster_checks.utils.enums import Status


class TestStructedPrinter:
    """Test StructedPrinter JSON formatting."""

    def test_print_to_json_creates_file(self, tmp_path):
        """Test that print_to_json creates a JSON file."""
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
