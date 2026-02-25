"""
Unit tests for Blueprint Hardware Rule.

Tests the Blueprint hardware validation rule including data collection,
uniformity checking, and result formatting.
"""

from collections import OrderedDict
from unittest.mock import Mock, patch

import pytest

from openshift_in_cluster_checks.rules.hw_fw_details.hardware_rule import HardwareDetailsRule
from openshift_in_cluster_checks.rules.hw_fw_details.collectors.cpu_collectors import ProcessorType
from openshift_in_cluster_checks.utils.enums import Status


class TestHardwareDetailsRule:
    """Test HardwareDetailsRule class."""

    def test_get_data_collectors(self):
        """Test that rule returns correct data collectors."""
        rule = HardwareDetailsRule()
        collectors = rule.get_data_collectors()

        assert ProcessorType in collectors
        assert len(collectors) >= 1

    def test_check_group_uniformity_uniform(self):
        """Test uniformity check with uniform data."""
        rule = HardwareDetailsRule()

        # All nodes have identical data
        group_data = {
            "master-0": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
            "master-1": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
            "master-2": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
        }

        result = rule._check_group_uniformity(group_data)
        assert result is True

    def test_check_group_uniformity_mixed(self):
        """Test uniformity check with mixed data."""
        rule = HardwareDetailsRule()

        # Some nodes have different data
        group_data = {
            "worker-0": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
            "worker-1": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
            "worker-2": {"CPU0": "Intel Xeon Gold 6230", "CPU1": "Intel Xeon Gold 6230"},
        }

        result = rule._check_group_uniformity(group_data)
        assert result is False

    def test_check_group_uniformity_single_node(self):
        """Test uniformity check with single node."""
        rule = HardwareDetailsRule()

        group_data = {
            "master-0": {"CPU0": "Intel Xeon Gold 6238"}
        }

        result = rule._check_group_uniformity(group_data)
        assert result is True

    def test_get_list_of_id_host_name_data_format(self):
        """Test HC Blueprint format for non-uniform values."""
        rule = HardwareDetailsRule()

        # Input: {node_name: {component_id: value}}
        group_data = {
            "worker-0": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
            "worker-1": {"CPU0": "Intel Xeon Gold 6230", "CPU1": "Intel Xeon Gold 6230"}
        }

        result = rule._get_list_of_id_host_name_data(group_data)

        # Expected HC format: list of {component_id: {hostname: value}}
        expected = [
            {
                "CPU0": {"worker-0": "Intel Xeon Gold 6238"},
                "CPU1": {"worker-0": "Intel Xeon Gold 6238"}
            },
            {
                "CPU0": {"worker-1": "Intel Xeon Gold 6230"},
                "CPU1": {"worker-1": "Intel Xeon Gold 6230"}
            }
        ]

        assert isinstance(result, list)
        assert len(result) == 2
        assert result == expected

    def test_get_list_of_id_host_name_data_with_none(self):
        """Test HC Blueprint format when node data is None."""
        rule = HardwareDetailsRule()

        group_data = {
            "worker-0": {"CPU0": "Intel Xeon Gold 6238"},
            "worker-1": None
        }

        result = rule._get_list_of_id_host_name_data(group_data)

        assert isinstance(result, list)
        assert len(result) == 2
        # First entry has data
        assert "CPU0" in result[0]
        assert result[0]["CPU0"] == {"worker-0": "Intel Xeon Gold 6238"}
        # Second entry is empty dict due to None
        assert result[1] == {}

    def test_compare_within_groups_uniform(self):
        """Test compare_within_groups with uniform data."""
        rule = HardwareDetailsRule()

        # Mock node executors
        executor1 = Mock()
        executor1.node_name = "master-0"

        executor2 = Mock()
        executor2.node_name = "master-1"

        node_groups = {
            "control-plane,master,worker": [executor1, executor2]
        }

        # Mock collected data - uniform across nodes
        collected_data = {
            "ProcessorType": {
                "master-0": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
                "master-1": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"}
            }
        }

        result = rule.compare_within_groups(collected_data, node_groups)

        # Check result structure
        assert result.status == Status.INFO
        assert "uniform" in result.message.lower()
        assert result.extra is not None
        assert "blueprint_data" in result.extra

        # Check blueprint data structure
        blueprint_data = result.extra["blueprint_data"]
        assert "control-plane,master,worker" in blueprint_data

        group_data = blueprint_data["control-plane,master,worker"]
        assert group_data["node_count"] == 2
        assert group_data["nodes"] == ["master-0", "master-1"]
        assert "hardware" in group_data

        # Check hardware data (HC nested format: topic -> name)
        hw_data = group_data["hardware"]["Processor"]["type"]
        assert hw_data["is_uniform"] is True
        assert "value" in hw_data
        # When uniform, value should be the representative value
        assert hw_data["value"] == {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"}

    def test_compare_within_groups_mixed(self):
        """Test compare_within_groups with mixed data (HC format)."""
        rule = HardwareDetailsRule()

        # Mock node executors
        executor1 = Mock()
        executor1.node_name = "worker-0"

        executor2 = Mock()
        executor2.node_name = "worker-1"

        executor3 = Mock()
        executor3.node_name = "worker-2"

        node_groups = {
            "worker": [executor1, executor2, executor3]
        }

        # Mock collected data - mixed across nodes
        collected_data = {
            "ProcessorType": {
                "worker-0": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
                "worker-1": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
                "worker-2": {"CPU0": "Intel Xeon Gold 6230", "CPU1": "Intel Xeon Gold 6230"}
            }
        }

        result = rule.compare_within_groups(collected_data, node_groups)

        # Check result structure
        assert result.status == Status.INFO
        assert "mixed" in result.message.lower()
        assert result.extra is not None
        assert "blueprint_data" in result.extra

        # Check blueprint data structure
        blueprint_data = result.extra["blueprint_data"]
        assert "worker" in blueprint_data

        group_data = blueprint_data["worker"]
        assert group_data["node_count"] == 3
        assert set(group_data["nodes"]) == {"worker-0", "worker-1", "worker-2"}

        # Check hardware data (HC nested format: topic -> name)
        hw_data = group_data["hardware"]["Processor"]["type"]
        assert hw_data["is_uniform"] is False
        assert "value" in hw_data

        # When not uniform, value should be HC format: list of {component_id: {hostname: value}}
        value_list = hw_data["value"]
        assert isinstance(value_list, list)
        assert len(value_list) == 3

        # Each entry should be {component_id: {hostname: value}}
        for entry in value_list:
            assert isinstance(entry, dict)
            assert "CPU0" in entry
            assert "CPU1" in entry

            # Each component should have {hostname: value}
            for component_id, host_value in entry.items():
                assert isinstance(host_value, dict)
                assert len(host_value) == 1  # One hostname per entry
                hostname = list(host_value.keys())[0]
                assert hostname in ["worker-0", "worker-1", "worker-2"]

        # Verify specific values match expected HC format
        # Should have entries like: {"CPU0": {"worker-0": "..."},  "CPU1": {"worker-0": "..."}}
        hostnames_found = []
        for entry in value_list:
            # Get hostname from first component
            hostname = list(entry["CPU0"].keys())[0]
            hostnames_found.append(hostname)

            # Verify both CPUs reference same hostname
            assert list(entry["CPU1"].keys())[0] == hostname

        # All nodes should be represented
        assert set(hostnames_found) == {"worker-0", "worker-1", "worker-2"}

    def test_compare_within_groups_multiple_groups(self):
        """Test compare_within_groups with multiple node groups."""
        rule = HardwareDetailsRule()

        # Mock executors for different groups
        master1 = Mock()
        master1.node_name = "master-0"
        master2 = Mock()
        master2.node_name = "master-1"

        worker1 = Mock()
        worker1.node_name = "worker-0"
        worker2 = Mock()
        worker2.node_name = "worker-1"

        node_groups = {
            "control-plane,master,worker": [master1, master2],
            "worker": [worker1, worker2]
        }

        # Uniform masters, mixed workers
        collected_data = {
            "ProcessorType": {
                "master-0": {"CPU0": "Intel Xeon Gold 6238"},
                "master-1": {"CPU0": "Intel Xeon Gold 6238"},
                "worker-0": {"CPU0": "Intel Xeon Gold 6238"},
                "worker-1": {"CPU0": "Intel Xeon Gold 6230"}
            }
        }

        result = rule.compare_within_groups(collected_data, node_groups)

        # Overall should be mixed (not all uniform)
        assert result.status == Status.INFO
        assert "mixed" in result.message.lower()

        blueprint_data = result.extra["blueprint_data"]

        # Masters should be uniform (HC nested format)
        masters_hw = blueprint_data["control-plane,master,worker"]["hardware"]["Processor"]["type"]
        assert masters_hw["is_uniform"] is True
        assert masters_hw["value"] == {"CPU0": "Intel Xeon Gold 6238"}

        # Workers should be mixed (HC nested format)
        workers_hw = blueprint_data["worker"]["hardware"]["Processor"]["type"]
        assert workers_hw["is_uniform"] is False
        assert isinstance(workers_hw["value"], list)
        assert len(workers_hw["value"]) == 2


    def test_parse_objective_name(self):
        """Test parsing objective names in HC format."""
        rule = HardwareDetailsRule()

        topic, name = rule._parse_objective_name("Processor@type")
        assert topic == "Processor"
        assert name == "type"

        # Should raise assertion error for invalid format
        with pytest.raises(AssertionError):
            rule._parse_objective_name("invalid")

    def test_run_rule_hc_nested_format(self):
        """
        Test run_rule() returns HC Blueprint nested structure (topic -> name).

        Scenario: 2 workers with Gold 6238, 1 worker with Gold 6230 (mixed).

        Expected HC structure:
        {
          "worker": {
            "hardware": {
              "Processor": {"type": {"is_uniform": False, "value": [...]}}
            }
          }
        }
        """
        worker1 = Mock()
        worker1.node_name = "worker-0"
        worker1.node_labels = "worker"

        worker2 = Mock()
        worker2.node_name = "worker-1"
        worker2.node_labels = "worker"

        worker3 = Mock()
        worker3.node_name = "worker-2"
        worker3.node_labels = "worker"

        rule = HardwareDetailsRule()
        rule._node_executors = {"worker-0": worker1, "worker-1": worker2, "worker-2": worker3}

        # 2 workers same CPU, 1 different
        mock_data = {
            "worker-0": {"CPU0": "Intel Xeon Gold 6238"},
            "worker-1": {"CPU0": "Intel Xeon Gold 6238"},
            "worker-2": {"CPU0": "Intel Xeon Gold 6230"}
        }

        def mock_run_dc(*args, **kwargs):
            rule.any_passed_data_collector = True
            return mock_data

        with patch.object(rule, 'run_data_collector', side_effect=mock_run_dc):
            result = rule.run_rule()

        # Expected HC Blueprint nested format: topic -> name
        # Since all collectors are mocked to return the same CPU data,
        # all properties will show the same values
        mock_value = [
            {"CPU0": {"worker-0": "Intel Xeon Gold 6238"}},
            {"CPU0": {"worker-1": "Intel Xeon Gold 6238"}},
            {"CPU0": {"worker-2": "Intel Xeon Gold 6230"}}
        ]

        expected = {
            "worker": {
                "node_count": 3,
                "nodes": ["worker-0", "worker-1", "worker-2"],
                "hardware": {
                    "Processor": {
                        "type": {"is_uniform": False, "value": mock_value},
                        "frequency_in_mhz": {"is_uniform": False, "value": mock_value},
                        "number_of_threads_per_core": {"is_uniform": False, "value": mock_value},
                        "number_of_physical_cores_per_processor": {"is_uniform": False, "value": mock_value},
                    },
                    "CPU": {
                        "isolated": {"is_uniform": False, "value": mock_value},
                    },
                    "Memory": {
                        "size_in_mb": {"is_uniform": False, "value": mock_value},
                        "type": {"is_uniform": False, "value": mock_value},
                        "speed_in_mhz": {"is_uniform": False, "value": mock_value},
                    },
                    "Total memory": {
                        "total_size_in_mb": {"is_uniform": False, "value": mock_value},
                    },
                    "Numa": {
                        "total_allocated_memory_in_mb": {"is_uniform": False, "value": mock_value},
                        "cpus_per_numa": {"is_uniform": False, "value": mock_value},
                    },
                    "Network Interface": {
                        "vendor": {"is_uniform": False, "value": mock_value},
                        "model": {"is_uniform": False, "value": mock_value},
                        "speed_in_mb": {"is_uniform": False, "value": mock_value},
                        "ports_amount": {"is_uniform": False, "value": mock_value},
                        "ports_names": {"is_uniform": False, "value": mock_value},
                        "version": {"is_uniform": False, "value": mock_value},
                        "firmware": {"is_uniform": False, "value": mock_value},
                        "driver": {"is_uniform": False, "value": mock_value},
                    },
                    "Disk": {
                        "type": {"is_uniform": False, "value": mock_value},
                        "model": {"is_uniform": False, "value": mock_value},
                        "vendor": {"is_uniform": False, "value": mock_value},
                        "size_in_mb": {"is_uniform": False, "value": mock_value},
                    },
                    "operating_system_disk": {
                        "name": {"is_uniform": False, "value": mock_value},
                        "type": {"is_uniform": False, "value": mock_value},
                        "size_in_mb": {"is_uniform": False, "value": mock_value},
                    },
                    "Numa": {
                        "total_allocated_memory_in_mb": {"is_uniform": False, "value": mock_value},
                        "cpus_per_numa": {"is_uniform": False, "value": mock_value},
                        "nic_per_numa": {"is_uniform": False, "value": mock_value},
                    },
                }
            }
        }

        assert result.status == Status.INFO
        assert result.extra["blueprint_data"] == expected

    def test_multiple_properties_mixed_uniformity(self):
        """
        Test with multiple properties under same topic where some are uniform and some are mixed.

        Scenario:
        - Mock 2 collectors: ProcessorType and ProcessorFrequency (both under Processor topic)
        - CPU type: UNIFORM (all workers have same type)
        - CPU frequency: MIXED (workers have different frequencies)

        Expected structure:
        {
          "worker": {
            "hardware": {
              "Processor": {
                "type": {"is_uniform": True, "value": {...}},
                "frequency": {"is_uniform": False, "value": [...]}
              }
            }
          }
        }
        """
        # Mock processor frequency collector
        class MockProcessorFrequency(Mock):
            def get_objective_name(self):
                return "Processor@frequency"

        worker1 = Mock()
        worker1.node_name = "worker-0"
        worker1.node_labels = "worker"

        worker2 = Mock()
        worker2.node_name = "worker-1"
        worker2.node_labels = "worker"

        worker3 = Mock()
        worker3.node_name = "worker-2"
        worker3.node_labels = "worker"

        rule = HardwareDetailsRule()
        rule._node_executors = {"worker-0": worker1, "worker-1": worker2, "worker-2": worker3}

        # Create proper mock collector classes
        mock_type_collector_class = Mock()
        mock_type_collector_class.__name__ = "ProcessorType"
        mock_type_instance = Mock()
        mock_type_instance.get_objective_name.return_value = "Processor@type"
        mock_type_collector_class.return_value = mock_type_instance

        mock_freq_collector_class = Mock()
        mock_freq_collector_class.__name__ = "ProcessorFrequency"
        mock_freq_instance = Mock()
        mock_freq_instance.get_objective_name.return_value = "Processor@frequency"
        mock_freq_collector_class.return_value = mock_freq_instance

        with patch.object(rule, 'get_data_collectors', return_value=[mock_type_collector_class, mock_freq_collector_class]):
            # Mock collected data
            collected_data = {
                "ProcessorType": {
                    "worker-0": {"CPU0": "Intel Xeon Gold 6238"},
                    "worker-1": {"CPU0": "Intel Xeon Gold 6238"},
                    "worker-2": {"CPU0": "Intel Xeon Gold 6238"}  # All same - UNIFORM
                },
                "ProcessorFrequency": {
                    "worker-0": {"CPU0": "2.1 GHz"},
                    "worker-1": {"CPU0": "2.1 GHz"},
                    "worker-2": {"CPU0": "2.5 GHz"}  # One different - MIXED
                }
            }

            node_groups = {"worker": [worker1, worker2, worker3]}
            result = rule.compare_within_groups(collected_data, node_groups)

        # Check result
        assert result.status == Status.INFO
        assert "mixed" in result.message.lower()  # Overall mixed because frequency is mixed

        blueprint_data = result.extra["blueprint_data"]
        processor_data = blueprint_data["worker"]["hardware"]["Processor"]

        # Type should be uniform
        assert processor_data["type"]["is_uniform"] is True
        assert processor_data["type"]["value"] == {"CPU0": "Intel Xeon Gold 6238"}

        # Frequency should be mixed
        assert processor_data["frequency"]["is_uniform"] is False
        freq_values = processor_data["frequency"]["value"]
        assert isinstance(freq_values, list)
        assert len(freq_values) == 3
        # HC format: list of {component_id: {hostname: value}}
        assert freq_values[0] == {"CPU0": {"worker-0": "2.1 GHz"}}
        assert freq_values[1] == {"CPU0": {"worker-1": "2.1 GHz"}}
        assert freq_values[2] == {"CPU0": {"worker-2": "2.5 GHz"}}

    def test_run_rule_full_mixed_json_comparison(self):
        """
        Comprehensive test with run_rule() comparing complete expected JSON.

        Scenario:
        - 2 masters: UNIFORM for both type and frequency
        - 5 workers: MIXED for both type and frequency
          - worker-0,1,2: Intel Xeon Gold 6238 @ 2.1 GHz
          - worker-3,4: Intel Xeon Gold 6230 @ 2.5 GHz
        """
        # Create executors
        master1, master2 = Mock(), Mock()
        master1.node_name, master1.node_labels = "master-0", "control-plane,master,worker"
        master2.node_name, master2.node_labels = "master-1", "control-plane,master,worker"

        workers = [Mock() for _ in range(5)]
        for i, w in enumerate(workers):
            w.node_name, w.node_labels = f"worker-{i}", "worker"

        rule = HardwareDetailsRule()
        rule._node_executors = {
            "master-0": master1,
            "master-1": master2,
            **{f"worker-{i}": workers[i] for i in range(5)}
        }

        # Mock collector classes
        mock_type = Mock()
        mock_type.__name__ = "ProcessorType"
        mock_type.return_value.get_objective_name.return_value = "Processor@type"

        mock_freq = Mock()
        mock_freq.__name__ = "ProcessorFrequency"
        mock_freq.return_value.get_objective_name.return_value = "Processor@frequency"

        def mock_collector(cls):
            rule.any_passed_data_collector = True
            if cls.__name__ == "ProcessorType":
                return {
                    "master-0": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
                    "master-1": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
                    "worker-0": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
                    "worker-1": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
                    "worker-2": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
                    "worker-3": {"CPU0": "Intel Xeon Gold 6230", "CPU1": "Intel Xeon Gold 6230"},
                    "worker-4": {"CPU0": "Intel Xeon Gold 6230", "CPU1": "Intel Xeon Gold 6230"}
                }
            return {  # ProcessorFrequency
                "master-0": {"CPU0": "2.1 GHz", "CPU1": "2.1 GHz"},
                "master-1": {"CPU0": "2.1 GHz", "CPU1": "2.1 GHz"},
                "worker-0": {"CPU0": "2.1 GHz", "CPU1": "2.1 GHz"},
                "worker-1": {"CPU0": "2.1 GHz", "CPU1": "2.1 GHz"},
                "worker-2": {"CPU0": "2.1 GHz", "CPU1": "2.1 GHz"},
                "worker-3": {"CPU0": "2.5 GHz", "CPU1": "2.5 GHz"},
                "worker-4": {"CPU0": "2.5 GHz", "CPU1": "2.5 GHz"}
            }

        with patch.object(rule, 'get_data_collectors', return_value=[mock_type, mock_freq]):
            with patch.object(rule, 'run_data_collector', side_effect=mock_collector):
                result = rule.run_rule()

        # Build complete expected JSON in HC Blueprint format
        expected_blueprint_data = {
            "control-plane,master,worker": {
                "node_count": 2,
                "nodes": ["master-0", "master-1"],
                "hardware": {
                    "Processor": {
                        "type": {
                            "is_uniform": True,
                            "value": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"}
                        },
                        "frequency": {
                            "is_uniform": True,
                            "value": {"CPU0": "2.1 GHz", "CPU1": "2.1 GHz"}
                        }
                    }
                }
            },
            "worker": {
                "node_count": 5,
                "nodes": ["worker-0", "worker-1", "worker-2", "worker-3", "worker-4"],
                "hardware": {
                    "Processor": {
                        "type": {
                            "is_uniform": False,
                            "value": [
                                {"CPU0": {"worker-0": "Intel Xeon Gold 6238"}, "CPU1": {"worker-0": "Intel Xeon Gold 6238"}},
                                {"CPU0": {"worker-1": "Intel Xeon Gold 6238"}, "CPU1": {"worker-1": "Intel Xeon Gold 6238"}},
                                {"CPU0": {"worker-2": "Intel Xeon Gold 6238"}, "CPU1": {"worker-2": "Intel Xeon Gold 6238"}},
                                {"CPU0": {"worker-3": "Intel Xeon Gold 6230"}, "CPU1": {"worker-3": "Intel Xeon Gold 6230"}},
                                {"CPU0": {"worker-4": "Intel Xeon Gold 6230"}, "CPU1": {"worker-4": "Intel Xeon Gold 6230"}}
                            ]
                        },
                        "frequency": {
                            "is_uniform": False,
                            "value": [
                                {"CPU0": {"worker-0": "2.1 GHz"}, "CPU1": {"worker-0": "2.1 GHz"}},
                                {"CPU0": {"worker-1": "2.1 GHz"}, "CPU1": {"worker-1": "2.1 GHz"}},
                                {"CPU0": {"worker-2": "2.1 GHz"}, "CPU1": {"worker-2": "2.1 GHz"}},
                                {"CPU0": {"worker-3": "2.5 GHz"}, "CPU1": {"worker-3": "2.5 GHz"}},
                                {"CPU0": {"worker-4": "2.5 GHz"}, "CPU1": {"worker-4": "2.5 GHz"}}
                            ]
                        }
                    }
                }
            }
        }

        # Direct JSON comparison
        assert result.status == Status.INFO
        assert result.message == "Mixed hardware configurations detected - see 'HW & FW' tab for details"
        assert result.extra["blueprint_data"] == expected_blueprint_data
        assert result.extra["html_tab"] == "blueprint"
        assert result.extra["is_uniform"] is False

    def test_collect_all_data_handles_none_from_exceptions(self):
        """
        Test that _collect_all_data handles None data from failed collectors.

        When a collector raises an exception, run_data_collector returns None for that node.
        The rule should replace None with {"component_id": "---"} for all components.

        This follows HealthChecks pattern from BlueprintValidations._collected_data().
        """
        # Create executors
        worker1, worker2 = Mock(), Mock()
        worker1.node_name = "worker-0"
        worker2.node_name = "worker-1"

        rule = HardwareDetailsRule()
        rule._node_executors = {"worker-0": worker1, "worker-1": worker2}

        # Mock collector class
        mock_collector_class = Mock()
        mock_collector_class.__name__ = "ProcessorType"
        mock_collector_instance = Mock()
        mock_collector_instance.get_objective_name.return_value = "Processor@type"
        mock_collector_instance.get_component_ids.return_value = ["CPU0", "CPU1"]
        mock_collector_class.return_value = mock_collector_instance

        # Mock run_data_collector to return None for worker-1 (simulating exception)
        def mock_run_data_collector(cls):
            rule.any_passed_data_collector = True  # At least worker-0 succeeded
            return {
                "worker-0": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
                "worker-1": None  # Simulates exception during collection
            }

        with patch.object(rule, 'get_data_collectors', return_value=[mock_collector_class]):
            with patch.object(rule, 'run_data_collector', side_effect=mock_run_data_collector):
                node_groups = {"worker": [worker1, worker2]}
                collected_data = rule._collect_all_data(node_groups)

        # Verify that None was replaced with "---" for all component IDs
        assert "ProcessorType" in collected_data
        processor_data = collected_data["ProcessorType"]

        # worker-0 should have normal data
        assert processor_data["worker-0"] == {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"}

        # worker-1 should have "---" placeholders instead of None
        assert processor_data["worker-1"] is not None
        assert processor_data["worker-1"] == {"CPU0": "---", "CPU1": "---"}

    def test_compare_with_failed_collector(self):
        """
        Test that compare_within_groups properly handles nodes with "---" from failed collectors.

        Scenario:
        - worker-0: successful collection (Intel Xeon Gold 6238)
        - worker-1: failed collection (shows "---")

        Expected:
        - Group should be marked as non-uniform (because values differ)
        - worker-1 should show "---" in the output
        """
        # Create executors
        worker1, worker2 = Mock(), Mock()
        worker1.node_name, worker1.node_labels = "worker-0", "worker"
        worker2.node_name, worker2.node_labels = "worker-1", "worker"

        rule = HardwareDetailsRule()
        rule._node_executors = {"worker-0": worker1, "worker-1": worker2}

        # Mock collector
        mock_collector_class = Mock()
        mock_collector_class.__name__ = "ProcessorType"
        mock_collector_instance = Mock()
        mock_collector_instance.get_objective_name.return_value = "Processor@type"
        mock_collector_instance.get_component_ids.return_value = ["CPU0", "CPU1"]
        mock_collector_class.return_value = mock_collector_instance

        # Simulate: worker-0 succeeds, worker-1 fails (returns None, then replaced with "---")
        def mock_run_data_collector(cls):
            rule.any_passed_data_collector = True  # At least worker-0 succeeded
            return {
                "worker-0": {"CPU0": "Intel Xeon Gold 6238", "CPU1": "Intel Xeon Gold 6238"},
                "worker-1": None  # Will be replaced with "---"
            }

        with patch.object(rule, 'get_data_collectors', return_value=[mock_collector_class]):
            with patch.object(rule, 'run_data_collector', side_effect=mock_run_data_collector):
                result = rule.run_rule()

        # Verify result
        assert result.status == Status.INFO
        assert "mixed" in result.message.lower()  # Should be mixed because of "---" vs real data

        blueprint_data = result.extra["blueprint_data"]
        worker_group = blueprint_data["worker"]

        # Check hardware data
        processor_data = worker_group["hardware"]["Processor"]["type"]
        assert processor_data["is_uniform"] is False  # Not uniform because of "---"

        # Verify HC format: list of {component_id: {hostname: value}}
        value_list = processor_data["value"]
        assert isinstance(value_list, list)
        assert len(value_list) == 2

        # Find entries for each worker
        worker0_entry = next(e for e in value_list if "worker-0" in str(e))
        worker1_entry = next(e for e in value_list if "worker-1" in str(e))

        # worker-0 should have real data
        assert worker0_entry["CPU0"]["worker-0"] == "Intel Xeon Gold 6238"
        assert worker0_entry["CPU1"]["worker-0"] == "Intel Xeon Gold 6238"

        # worker-1 should have "---"
        assert worker1_entry["CPU0"]["worker-1"] == "---"
        assert worker1_entry["CPU1"]["worker-1"] == "---"
