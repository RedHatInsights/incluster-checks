"""Tests for DataCollectorRunner."""

import threading
from unittest.mock import Mock, patch

import pytest

from in_cluster_checks.core.data_collector_runner import DataCollectorRunner
from in_cluster_checks.utils.enums import Objectives
from in_cluster_checks.core.exceptions import UnExpectedSystemOutput

class TestDataCollectorRunner:
    """Test DataCollectorRunner functionality."""

    def setup_method(self):
        """Clear cache before each test."""
        DataCollectorRunner.clear_data_collector_cache()

    def teardown_method(self):
        """Clear cache after each test."""
        DataCollectorRunner.clear_data_collector_cache()

    def test_clear_data_collector_cache(self):
        """Test that cache clearing works."""
        # Add some data to cache
        DataCollectorRunner.data_collector_db[("test", "host", "{}")] = {"data": "test"}
        assert len(DataCollectorRunner.data_collector_db) == 1

        # Clear cache
        DataCollectorRunner.clear_data_collector_cache()

        assert len(DataCollectorRunner.data_collector_db) == 0

    def test_is_many_to_one_relationship_true(self):
        """Test many-to-one relationship detection (cache needed)."""
        # ALL_NODES -> ONE_MASTER is many-to-one
        result = DataCollectorRunner.is_many_to_one_relationship(
            [Objectives.ALL_NODES],
            [Objectives.ONE_MASTER]
        )
        assert result is True

        # WORKERS -> ONE_MASTER is many-to-one
        result = DataCollectorRunner.is_many_to_one_relationship(
            [Objectives.WORKERS],
            [Objectives.ONE_MASTER]
        )
        assert result is True

        # ALL_NODES -> ORCHESTRATOR is many-to-one
        result = DataCollectorRunner.is_many_to_one_relationship(
            [Objectives.ALL_NODES],
            [Objectives.ORCHESTRATOR]
        )
        assert result is True

    def test_is_many_to_one_relationship_false_one_to_one(self):
        """Test one-to-one relationship (no cache needed)."""
        # ONE_MASTER -> ONE_WORKER is one-to-one
        result = DataCollectorRunner.is_many_to_one_relationship(
            [Objectives.ONE_MASTER],
            [Objectives.ONE_WORKER]
        )
        assert result is False

        # ORCHESTRATOR -> ONE_MASTER is one-to-one (both single types)
        result = DataCollectorRunner.is_many_to_one_relationship(
            [Objectives.ORCHESTRATOR],
            [Objectives.ONE_MASTER]
        )
        assert result is False

    def test_is_many_to_one_relationship_false_one_to_many(self):
        """Test one-to-many relationship (no cache needed)."""
        # ONE_MASTER -> ALL_NODES is one-to-many
        result = DataCollectorRunner.is_many_to_one_relationship(
            [Objectives.ONE_MASTER],
            [Objectives.ALL_NODES]
        )
        assert result is False

        # ORCHESTRATOR -> ALL_NODES is one-to-many
        result = DataCollectorRunner.is_many_to_one_relationship(
            [Objectives.ORCHESTRATOR],
            [Objectives.ALL_NODES]
        )
        assert result is False

    def test_validate_data_collector_relationship_valid_one_to_one(self):
        """Test validation allows one-to-one relationships."""
        # Should not raise
        DataCollectorRunner.validate_data_collector_relationship(
            source_roles=[Objectives.ONE_MASTER],
            target_roles=[Objectives.ONE_WORKER],
            rule_name="TestRule",
            collector_name="TestCollector"
        )

    def test_validate_data_collector_relationship_valid_orchestrator_to_single(self):
        """Test validation allows ORCHESTRATOR -> single type relationships."""
        # ORCHESTRATOR -> ONE_MASTER (one-to-one)
        DataCollectorRunner.validate_data_collector_relationship(
            source_roles=[Objectives.ORCHESTRATOR],
            target_roles=[Objectives.ONE_MASTER],
            rule_name="TestRule",
            collector_name="TestCollector"
        )

        # ORCHESTRATOR -> ONE_WORKER (one-to-one)
        DataCollectorRunner.validate_data_collector_relationship(
            source_roles=[Objectives.ORCHESTRATOR],
            target_roles=[Objectives.ONE_WORKER],
            rule_name="TestRule",
            collector_name="TestCollector"
        )

    def test_validate_data_collector_relationship_valid_orchestrator_to_many(self):
        """Test validation allows ORCHESTRATOR -> multi-type relationships."""
        # ORCHESTRATOR -> ALL_NODES (one-to-many)
        DataCollectorRunner.validate_data_collector_relationship(
            source_roles=[Objectives.ORCHESTRATOR],
            target_roles=[Objectives.ALL_NODES],
            rule_name="TestRule",
            collector_name="TestCollector"
        )

        # ORCHESTRATOR -> WORKERS (one-to-many)
        DataCollectorRunner.validate_data_collector_relationship(
            source_roles=[Objectives.ORCHESTRATOR],
            target_roles=[Objectives.WORKERS],
            rule_name="TestRule",
            collector_name="TestCollector"
        )

    def test_validate_data_collector_relationship_valid_many_to_one(self):
        """Test validation allows many-to-one relationships."""
        # Should not raise
        DataCollectorRunner.validate_data_collector_relationship(
            source_roles=[Objectives.ALL_NODES],
            target_roles=[Objectives.ONE_MASTER],
            rule_name="TestRule",
            collector_name="TestCollector"
        )

    def test_validate_data_collector_relationship_valid_many_to_orchestrator(self):
        """Test validation allows many-to-ORCHESTRATOR relationships."""
        # ALL_NODES -> ORCHESTRATOR (many-to-one)
        DataCollectorRunner.validate_data_collector_relationship(
            source_roles=[Objectives.ALL_NODES],
            target_roles=[Objectives.ORCHESTRATOR],
            rule_name="TestRule",
            collector_name="TestCollector"
        )

        # WORKERS -> ORCHESTRATOR (many-to-one)
        DataCollectorRunner.validate_data_collector_relationship(
            source_roles=[Objectives.WORKERS],
            target_roles=[Objectives.ORCHESTRATOR],
            rule_name="TestRule",
            collector_name="TestCollector"
        )

    def test_validate_data_collector_relationship_valid_one_to_many(self):
        """Test validation allows one-to-many relationships."""
        # Should not raise
        DataCollectorRunner.validate_data_collector_relationship(
            source_roles=[Objectives.ONE_MASTER],
            target_roles=[Objectives.ALL_NODES],
            rule_name="TestRule",
            collector_name="TestCollector"
        )

    def test_validate_data_collector_relationship_invalid_many_to_many(self):
        """Test validation rejects many-to-many relationships."""
        with pytest.raises(AssertionError, match="does not support many-to-many relationships"):
            DataCollectorRunner.validate_data_collector_relationship(
                source_roles=[Objectives.ALL_NODES],
                target_roles=[Objectives.WORKERS],
                rule_name="TestRule",
                collector_name="TestCollector"
            )

    def test_validate_data_collector_relationship_invalid_masters_to_workers(self):
        """Test validation rejects MASTERS -> WORKERS (many-to-many)."""
        with pytest.raises(AssertionError, match="does not support many-to-many relationships"):
            DataCollectorRunner.validate_data_collector_relationship(
                source_roles=[Objectives.MASTERS],
                target_roles=[Objectives.WORKERS],
                rule_name="TestRule",
                collector_name="TestCollector"
            )

    def test_run_collectors_sequentially_success(self):
        """Test sequential collector execution without cache."""
        # Create mock collectors
        collector1 = Mock()
        collector1.get_host_name.return_value = "node1"
        collector1.collect_data.return_value = {"cpu": "Intel"}
        collector1.get_bash_cmd_lines.return_value = ["cmd1"]
        collector1.get_rule_log.return_value = ["log1"]

        collector2 = Mock()
        collector2.get_host_name.return_value = "node2"
        collector2.collect_data.return_value = {"cpu": "AMD"}
        collector2.get_bash_cmd_lines.return_value = ["cmd2"]
        collector2.get_rule_log.return_value = ["log2"]

        results_dict = {}

        DataCollectorRunner.run_collectors_sequentially(
            [collector1, collector2],
            results_dict
        )

        assert "node1" in results_dict
        assert results_dict["node1"]["data"] == {"cpu": "Intel"}
        assert results_dict["node1"]["exception"] is None
        assert results_dict["node1"]["bash_cmd_lines"] == ["cmd1"]
        assert results_dict["node1"]["rule_log"] == ["log1"]

        assert "node2" in results_dict
        assert results_dict["node2"]["data"] == {"cpu": "AMD"}
        assert results_dict["node2"]["exception"] is None

    def test_run_collectors_sequentially_with_exception(self):
        """Test sequential execution captures exceptions."""
        collector = Mock()
        collector.get_host_name.return_value = "node1"
        collector.collect_data.side_effect = Exception("Collection failed")
        collector.get_bash_cmd_lines.return_value = ["cmd1"]
        collector.get_rule_log.return_value = ["log1"]

        results_dict = {}

        DataCollectorRunner.run_collectors_sequentially(
            [collector],
            results_dict
        )

        assert "node1" in results_dict
        assert results_dict["node1"]["data"] is None
        assert isinstance(results_dict["node1"]["exception"], Exception)
        assert str(results_dict["node1"]["exception"]) == "Collection failed"
        assert results_dict["node1"]["bash_cmd_lines"] == ["cmd1"]
        assert results_dict["node1"]["rule_log"] == ["log1"]

    def test_run_data_collector_with_cache_cache_miss(self):
        """Test cache miss triggers data collection."""
        # Create mock collector with thread lock
        collector = Mock()
        collector.threadLock = threading.RLock()
        collector.__class__.__module__ = "test.module"
        collector.__class__.__name__ = "TestCollector"
        collector.get_host_name.return_value = "node1"
        collector.collect_data.return_value = {"cpu": "Intel"}
        collector.get_bash_cmd_lines.return_value = ["cmd1"]
        collector.get_rule_log.return_value = ["log1"]
        collector.add_to_rule_log = Mock()

        # Create mock rule instance
        mock_rule_instance = Mock()
        mock_rule_instance.unique_name = "TestRule"

        results_dict = {}

        DataCollectorRunner.run_data_collector_with_cache(
            collector,
            results_dict,
            mock_rule_instance,
            param1="value1"
        )

        # Verify data was collected
        collector.collect_data.assert_called_once_with(param1="value1")

        # Verify result stored in results_dict
        assert "node1" in results_dict
        assert results_dict["node1"]["data"] == {"cpu": "Intel"}
        assert results_dict["node1"]["exception"] is None

        # Verify cache populated
        cache_key = ("test.module.TestCollector", "node1", '{"param1": "value1"}')
        assert cache_key in DataCollectorRunner.data_collector_db

    def test_run_data_collector_with_cache_cache_hit(self):
        """Test cache hit skips data collection."""
        # Pre-populate cache
        cache_key = ("test.module.TestCollector", "node1", '{"param1": "value1"}')
        DataCollectorRunner.data_collector_db[cache_key] = {
            "data": {"cpu": "Cached Intel"},
            "exception": None,
            "bash_cmd_lines": ["cached_cmd"],
            "rule_log": ["cached_log"]
        }

        # Create mock collector
        collector = Mock()
        collector.threadLock = threading.RLock()
        collector.__class__.__module__ = "test.module"
        collector.__class__.__name__ = "TestCollector"
        collector.get_host_name.return_value = "node1"
        collector.add_to_rule_log = Mock()

        # Create mock rule instance
        mock_rule_instance = Mock()
        mock_rule_instance.unique_name = "TestRule"

        results_dict = {}

        DataCollectorRunner.run_data_collector_with_cache(
            collector,
            results_dict,
            mock_rule_instance,
            param1="value1"
        )

        # Verify collect_data was NOT called (cache hit)
        collector.collect_data.assert_not_called()

        # Verify cached data returned
        assert results_dict["node1"]["data"] == {"cpu": "Cached Intel"}
        assert results_dict["node1"]["bash_cmd_lines"] == ["cached_cmd"]

        # Verify cache hit message was added to rule_log
        assert len(results_dict["node1"]["rule_log"]) == 2  # Original log + cache hit message

    def test_load_data_collector_to_cache_success(self):
        """Test successful data loading into cache."""
        collector = Mock()
        collector.__class__.__module__ = "test.module"
        collector.__class__.__name__ = "TestCollector"
        collector.get_host_name.return_value = "node1"
        collector.collect_data.return_value = {"memory": "16GB"}
        collector.get_bash_cmd_lines.return_value = ["mem_cmd"]
        collector.get_rule_log.return_value = ["mem_log"]

        # Create mock rule instance
        mock_rule_instance = Mock()
        mock_rule_instance.unique_name = "TestRule"

        cache_key = ("test.module.TestCollector", "node1", "{}")

        DataCollectorRunner._load_data_collector_to_cache(
            collector,
            cache_key,
            mock_rule_instance
        )

        # Verify cache populated
        assert cache_key in DataCollectorRunner.data_collector_db
        cached = DataCollectorRunner.data_collector_db[cache_key]
        assert cached["data"] == {"memory": "16GB"}
        assert cached["exception"] is None
        assert cached["bash_cmd_lines"] == ["mem_cmd"]
        assert cached["rule_log"] == ["mem_log"]

    def test_load_data_collector_to_cache_exception(self):
        """Test exception during collection is cached."""
        collector = Mock()
        collector.__class__.__module__ = "test.module"
        collector.__class__.__name__ = "TestCollector"
        collector.get_host_name.return_value = "node1"
        collector.collect_data.side_effect = Exception("Hardware read failed")
        collector.get_bash_cmd_lines.return_value = ["failed_cmd"]
        collector.get_rule_log.return_value = ["failed_log"]

        # Create mock rule instance
        mock_rule_instance = Mock()
        mock_rule_instance.unique_name = "TestRule"

        cache_key = ("test.module.TestCollector", "node1", "{}")

        DataCollectorRunner._load_data_collector_to_cache(
            collector,
            cache_key,
            mock_rule_instance
        )

        # Verify exception cached
        assert cache_key in DataCollectorRunner.data_collector_db
        cached = DataCollectorRunner.data_collector_db[cache_key]
        assert cached["data"] is None
        assert isinstance(cached["exception"], Exception)
        assert str(cached["exception"]) == "Hardware read failed"
        assert cached["bash_cmd_lines"] == ["failed_cmd"]

    @patch('in_cluster_checks.core.data_collector_runner.ParallelRunner')
    def test_run_collectors_many_to_one_parallel(self, mock_parallel_runner):
        """Test many-to-one relationship uses cache and parallel execution."""
        # Setup mock collector instances
        collector_instances = [Mock(), Mock()]

        # Mock collector class with many-to-one relationship
        mock_collector_class = Mock()
        mock_collector_class.objective_hosts = [Objectives.ONE_MASTER]

        # Mock rule instance
        mock_rule_instance = Mock()
        mock_rule_instance.objective_hosts = [Objectives.ALL_NODES]

        DataCollectorRunner.run_collectors(
            collector_instances,
            use_parallel=True,
            collector_class=mock_collector_class,
            rule_instance=mock_rule_instance,
            param="value"
        )

        # Verify parallel runner called with cache method
        mock_parallel_runner.run_in_parallel.assert_called_once()
        call_args = mock_parallel_runner.run_in_parallel.call_args
        assert call_args[0][0] == collector_instances
        assert call_args[0][1] == DataCollectorRunner.run_data_collector_with_cache
        assert call_args[1]["param"] == "value"

    @patch('in_cluster_checks.core.data_collector_runner.ParallelRunner')
    def test_run_collectors_many_to_orchestrator_parallel(self, mock_parallel_runner):
        """Test many-to-ORCHESTRATOR relationship uses cache and parallel execution."""
        # Setup mock collector instances
        collector_instances = [Mock(), Mock()]

        # Mock collector class with ORCHESTRATOR target
        mock_collector_class = Mock()
        mock_collector_class.objective_hosts = [Objectives.ORCHESTRATOR]

        # Mock rule instance with multi-type source
        mock_rule_instance = Mock()
        mock_rule_instance.objective_hosts = [Objectives.ALL_NODES]

        DataCollectorRunner.run_collectors(
            collector_instances,
            use_parallel=True,
            collector_class=mock_collector_class,
            rule_instance=mock_rule_instance,
            param="value"
        )

        # Verify parallel runner called with cache method (many-to-one)
        mock_parallel_runner.run_in_parallel.assert_called_once()
        call_args = mock_parallel_runner.run_in_parallel.call_args
        assert call_args[0][0] == collector_instances
        assert call_args[0][1] == DataCollectorRunner.run_data_collector_with_cache

    def test_run_collectors_many_to_one_sequential(self):
        """Test many-to-one relationship uses cache with sequential execution."""
        # Create mock collector with thread lock
        collector = Mock()
        collector.threadLock = threading.RLock()
        collector.__class__.__module__ = "test.module"
        collector.__class__.__name__ = "TestCollector"
        collector.get_host_name.return_value = "node1"
        collector.collect_data.return_value = {"data": "test"}
        collector.get_bash_cmd_lines.return_value = []
        collector.get_rule_log.return_value = []
        collector.add_to_rule_log = Mock()

        # Mock collector class with many-to-one relationship
        mock_collector_class = Mock()
        mock_collector_class.objective_hosts = [Objectives.ONE_MASTER]

        # Mock rule instance
        mock_rule_instance = Mock()
        mock_rule_instance.objective_hosts = [Objectives.ALL_NODES]
        mock_rule_instance.unique_name = "TestRule"

        results = DataCollectorRunner.run_collectors(
            [collector],
            use_parallel=False,
            collector_class=mock_collector_class,
            rule_instance=mock_rule_instance
        )

        # Verify results returned
        assert "node1" in results
        assert results["node1"]["data"] == {"data": "test"}

        # Verify cache was used
        cache_key = ("test.module.TestCollector", "node1", "{}")
        assert cache_key in DataCollectorRunner.data_collector_db

    @patch('in_cluster_checks.core.data_collector_runner.ParallelRunner')
    def test_run_collectors_one_to_many_parallel(self, mock_parallel_runner):
        """Test one-to-many relationship uses parallel without cache."""
        collector_instances = [Mock(), Mock()]

        # Mock collector class with one-to-many relationship
        mock_collector_class = Mock()
        mock_collector_class.objective_hosts = [Objectives.ALL_NODES]

        # Mock rule instance
        mock_rule_instance = Mock()
        mock_rule_instance.objective_hosts = [Objectives.ONE_MASTER]

        DataCollectorRunner.run_collectors(
            collector_instances,
            use_parallel=True,
            collector_class=mock_collector_class,
            rule_instance=mock_rule_instance,
            param="value"
        )

        # Verify parallel runner called WITHOUT cache method
        mock_parallel_runner.run_data_collectors_in_parallel.assert_called_once()
        call_args = mock_parallel_runner.run_data_collectors_in_parallel.call_args
        assert call_args[0][0] == collector_instances
        assert call_args[1]["param"] == "value"

    @patch('in_cluster_checks.core.data_collector_runner.ParallelRunner')
    def test_run_collectors_orchestrator_to_many_parallel(self, mock_parallel_runner):
        """Test ORCHESTRATOR-to-many relationship uses parallel without cache."""
        collector_instances = [Mock(), Mock()]

        # Mock collector class with multi-type target
        mock_collector_class = Mock()
        mock_collector_class.objective_hosts = [Objectives.ALL_NODES]

        # Mock rule instance with ORCHESTRATOR source
        mock_rule_instance = Mock()
        mock_rule_instance.objective_hosts = [Objectives.ORCHESTRATOR]

        DataCollectorRunner.run_collectors(
            collector_instances,
            use_parallel=True,
            collector_class=mock_collector_class,
            rule_instance=mock_rule_instance,
            param="value"
        )

        # Verify parallel runner called WITHOUT cache method (one-to-many)
        mock_parallel_runner.run_data_collectors_in_parallel.assert_called_once()

    def test_run_collectors_one_to_one_sequential(self):
        """Test one-to-one relationship uses sequential without cache."""
        # Create mock collector
        collector = Mock()
        collector.get_host_name.return_value = "node1"
        collector.collect_data.return_value = {"data": "test"}
        collector.get_bash_cmd_lines.return_value = []
        collector.get_rule_log.return_value = []

        # Mock collector class with one-to-one relationship
        mock_collector_class = Mock()
        mock_collector_class.objective_hosts = [Objectives.ONE_WORKER]

        # Mock rule instance
        mock_rule_instance = Mock()
        mock_rule_instance.objective_hosts = [Objectives.ONE_MASTER]

        results = DataCollectorRunner.run_collectors(
            [collector],
            use_parallel=False,
            collector_class=mock_collector_class,
            rule_instance=mock_rule_instance
        )

        # Verify results returned
        assert "node1" in results
        assert results["node1"]["data"] == {"data": "test"}

        # Verify cache was NOT used (no cache key in db)
        assert len(DataCollectorRunner.data_collector_db) == 0

    def test_run_collectors_orchestrator_to_single_sequential(self):
        """Test ORCHESTRATOR-to-single relationship uses sequential without cache."""
        # Create mock collector
        collector = Mock()
        collector.get_host_name.return_value = "master-1"
        collector.collect_data.return_value = {"data": "test"}
        collector.get_bash_cmd_lines.return_value = []
        collector.get_rule_log.return_value = []

        # Mock collector class with single-type target
        mock_collector_class = Mock()
        mock_collector_class.objective_hosts = [Objectives.ONE_MASTER]

        # Mock rule instance with ORCHESTRATOR source
        mock_rule_instance = Mock()
        mock_rule_instance.objective_hosts = [Objectives.ORCHESTRATOR]

        results = DataCollectorRunner.run_collectors(
            [collector],
            use_parallel=False,
            collector_class=mock_collector_class,
            rule_instance=mock_rule_instance
        )

        # Verify results returned
        assert "master-1" in results
        assert results["master-1"]["data"] == {"data": "test"}

        # Verify cache was NOT used (one-to-one, no cache needed)
        assert len(DataCollectorRunner.data_collector_db) == 0

    @patch('in_cluster_checks.core.data_collector_runner.DataCollectorRunner.run_collectors')
    @patch('in_cluster_checks.core.data_collector_runner.DataCollectorRunner.get_data_collector_hosts_dict')
    def test_run_data_collector_integration(self, mock_get_hosts_dict, mock_run_collectors):
        """Test full run_data_collector workflow."""
        # Mock collector class
        mock_collector_class = Mock()
        mock_collector_class.__name__ = "TestCollector"
        mock_collector_class.objective_hosts = [Objectives.ONE_MASTER]
        mock_collector_class.raise_collection_errors = True

        # Mock collector instance
        mock_collector = Mock()
        mock_collector.get_host_name.return_value = "master-1"
        mock_collector.collect_data.return_value = {"result": "success"}
        mock_collector.get_bash_cmd_lines.return_value = []
        mock_collector.get_rule_log.return_value = []

        # Mock rule instance
        mock_rule_instance = Mock()
        mock_rule_instance.objective_hosts = [Objectives.ALL_NODES]
        mock_rule_instance.unique_name = "TestRule"
        mock_rule_instance._node_executors = {"master-1": Mock()}
        mock_rule_instance._bash_cmd_lines = []
        mock_rule_instance._rule_log = []
        mock_rule_instance.data_collector_exceptions = {}
        mock_rule_instance.any_passed_data_collector = False

        # Mock helper methods
        mock_get_hosts_dict.return_value = {
            "master-1": Mock()
        }
        mock_rule_instance._create_collector_instances.return_value = [mock_collector]

        # Mock run_collectors to return expected results
        mock_run_collectors.return_value = {
            "master-1": {
                "data": {"result": "success"},
                "exception": None,
                "bash_cmd_lines": [],
                "rule_log": []
            }
        }

        # Execute
        result = DataCollectorRunner.execute_data_collector(
            mock_rule_instance,
            mock_collector_class,
            use_parallel=False
        )

        # Verify
        assert result == {"master-1": {"result": "success"}}
        mock_get_hosts_dict.assert_called_once_with(
            mock_rule_instance._node_executors,
            mock_collector_class.objective_hosts
        )
        mock_rule_instance._create_collector_instances.assert_called_once()
        mock_run_collectors.assert_called_once()
        assert mock_rule_instance.any_passed_data_collector is True

    @patch('in_cluster_checks.core.data_collector_runner.DataCollectorRunner.get_data_collector_hosts_dict')
    def test_run_data_collector_no_hosts(self, mock_get_hosts_dict):
        """Test run_data_collector returns empty dict when no hosts."""
        mock_collector_class = Mock()
        mock_collector_class.__name__ = "TestCollector"
        mock_collector_class.objective_hosts = [Objectives.ONE_MASTER]

        mock_rule_instance = Mock()
        mock_rule_instance.objective_hosts = [Objectives.ALL_NODES]
        mock_rule_instance.unique_name = "TestRule"
        mock_rule_instance._node_executors = {}
        mock_get_hosts_dict.return_value = {}

        result = DataCollectorRunner.execute_data_collector(
            mock_rule_instance,
            mock_collector_class
        )

        assert result == {}

    @patch('in_cluster_checks.core.data_collector_runner.DataCollectorRunner.get_data_collector_hosts_dict')
    def test_run_data_collector_no_collector_instances(self, mock_get_hosts_dict):
        """Test run_data_collector returns empty dict when no collector instances."""
        mock_collector_class = Mock()
        mock_collector_class.__name__ = "TestCollector"
        mock_collector_class.objective_hosts = [Objectives.ONE_MASTER]

        mock_rule_instance = Mock()
        mock_rule_instance.objective_hosts = [Objectives.ALL_NODES]
        mock_rule_instance.unique_name = "TestRule"
        mock_rule_instance._node_executors = {"master-1": Mock()}
        mock_get_hosts_dict.return_value = {"master-1": Mock()}
        mock_rule_instance._create_collector_instances.return_value = []

        result = DataCollectorRunner.execute_data_collector(
            mock_rule_instance,
            mock_collector_class
        )

        assert result == {}

    def test_cache_thread_safety(self):
        """Test that cache is thread-safe for concurrent access."""
        collector_calls = []

        def mock_collect_data():
            """Simulate slow collection to test concurrency."""
            import time
            collector_calls.append("start")
            time.sleep(0.05)
            collector_calls.append("end")
            return {"data": "test"}

        # Create two collectors pointing to same host
        collector1 = Mock()
        collector1.threadLock = threading.RLock()
        collector1.__class__.__module__ = "test.module"
        collector1.__class__.__name__ = "TestCollector"
        collector1.get_host_name.return_value = "node1"
        collector1.collect_data = mock_collect_data
        collector1.get_bash_cmd_lines.return_value = []
        collector1.get_rule_log.return_value = []
        collector1.add_to_rule_log = Mock()

        collector2 = Mock()
        collector2.threadLock = collector1.threadLock  # Share lock
        collector2.__class__.__module__ = "test.module"
        collector2.__class__.__name__ = "TestCollector"
        collector2.get_host_name.return_value = "node1"
        collector2.collect_data = mock_collect_data
        collector2.get_bash_cmd_lines.return_value = []
        collector2.get_rule_log.return_value = []
        collector2.add_to_rule_log = Mock()

        # Create mock rule instance
        mock_rule_instance = Mock()
        mock_rule_instance.unique_name = "TestRule"

        results_dict = {}

        def run_collector(collector):
            DataCollectorRunner.run_data_collector_with_cache(
                collector,
                results_dict,
                mock_rule_instance
            )

        # Run both collectors in parallel
        thread1 = threading.Thread(target=run_collector, args=(collector1,))
        thread2 = threading.Thread(target=run_collector, args=(collector2,))

        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()

        # With thread safety, only one collection should happen
        # The lock ensures only one thread executes collection
        assert len(collector_calls) == 2  # One collection: start + end
        assert collector_calls == ["start", "end"]

        # Verify both results populated from cache
        assert "node1" in results_dict
        assert results_dict["node1"]["data"] == {"data": "test"}

    def test_aggregate_collector_results_success(self):
        """Test successful result aggregation."""
        mock_rule = Mock()
        mock_rule._bash_cmd_lines = []
        mock_rule._rule_log = []

        results_dict = {
            "node1": {
                "data": {"cpu": "Intel"},
                "exception": None,
                "bash_cmd_lines": ["cmd1", "cmd2"],
                "rule_log": ["log1", "log2"]
            },
            "node2": {
                "data": {"cpu": "AMD"},
                "exception": None,
                "bash_cmd_lines": ["cmd3"],
                "rule_log": ["log3"]
            }
        }

        aggregated = DataCollectorRunner.aggregate_collector_results(mock_rule, results_dict)

        assert aggregated["simple_results"] == {
            "node1": {"cpu": "Intel"},
            "node2": {"cpu": "AMD"}
        }
        assert aggregated["host_exceptions"] == {}
        assert mock_rule._bash_cmd_lines == ["cmd1", "cmd2", "cmd3"]
        assert mock_rule._rule_log == ["log1", "log2", "log3"]

    def test_aggregate_collector_results_with_exceptions(self):
        """Test result aggregation with exceptions."""
        mock_rule = Mock()
        mock_rule._bash_cmd_lines = []
        mock_rule._rule_log = []

        exception = Exception("Collection failed")
        results_dict = {
            "node1": {
                "data": None,
                "exception": exception,
                "bash_cmd_lines": ["cmd1"],
                "rule_log": ["log1"]
            }
        }

        aggregated = DataCollectorRunner.aggregate_collector_results(mock_rule, results_dict)

        assert aggregated["simple_results"] == {"node1": None}
        assert aggregated["host_exceptions"] == {"node1": exception}
        assert len(mock_rule._rule_log) == 2  # Original log + error
        assert "[node1] ERROR: Collection failed" in mock_rule._rule_log

    def test_is_collector_failed_on_all_hosts_true(self):
        """Test detection when collector failed on all hosts."""
        host_exceptions = {"node1": "error1", "node2": "error2"}
        hosts_dict = {"node1": Mock(), "node2": Mock()}

        result = DataCollectorRunner.is_collector_failed_on_all_hosts(host_exceptions, hosts_dict)

        assert result is True

    def test_is_collector_failed_on_all_hosts_false_partial(self):
        """Test detection when collector failed only on some hosts."""
        host_exceptions = {"node1": "error1"}
        hosts_dict = {"node1": Mock(), "node2": Mock()}

        result = DataCollectorRunner.is_collector_failed_on_all_hosts(host_exceptions, hosts_dict)

        assert result is False

    def test_is_collector_failed_on_all_hosts_false_no_exceptions(self):
        """Test detection when collector succeeded on all hosts."""
        host_exceptions = {}
        hosts_dict = {"node1": Mock(), "node2": Mock()}

        result = DataCollectorRunner.is_collector_failed_on_all_hosts(host_exceptions, hosts_dict)

        assert not result

    def test_format_collector_exceptions(self):
        """Test exception formatting for display."""
        host_exceptions = {
            "node1": "Error line 1\nError line 2",
            "node2": "Single error"
        }

        output = DataCollectorRunner.format_collector_exceptions("TestCollector", host_exceptions)

        assert output[0] == "[TestCollector]"
        assert "  [node1]" in output
        assert "    Error line 1" in output
        assert "    Error line 2" in output
        assert "  [node2]" in output
        assert "    Single error" in output
        assert output[-1] == ""  # Empty line at end

    def test_handle_collector_failures_all_failed(self):
        """Test handling when collector failed on all hosts."""

        mock_rule = Mock()
        mock_rule.data_collector_exceptions = {}
        mock_rule.any_passed_data_collector = False

        mock_collector_class = Mock()
        mock_collector_class.__name__ = "TestCollector"
        mock_collector_class.raise_collection_errors = True

        host_exceptions = {"node1": "error1", "node2": "error2"}
        hosts_dict = {"node1": Mock(), "node2": Mock()}

        with pytest.raises(UnExpectedSystemOutput, match="failed on all hosts"):
            DataCollectorRunner.handle_collector_failures(
                mock_rule, mock_collector_class, host_exceptions, hosts_dict
            )

        assert "TestCollector" in mock_rule.data_collector_exceptions
        assert mock_rule.any_passed_data_collector is False

    def test_handle_collector_failures_partial_success(self):
        """Test handling when collector succeeded on at least one host."""
        mock_rule = Mock()
        mock_rule.data_collector_exceptions = {}
        mock_rule.any_passed_data_collector = False

        mock_collector_class = Mock()
        mock_collector_class.__name__ = "TestCollector"

        host_exceptions = {"node1": "error1"}
        hosts_dict = {"node1": Mock(), "node2": Mock()}

        DataCollectorRunner.handle_collector_failures(
            mock_rule, mock_collector_class, host_exceptions, hosts_dict
        )

        assert "TestCollector" in mock_rule.data_collector_exceptions
        assert mock_rule.any_passed_data_collector is True

    def test_handle_collector_failures_no_raise_on_all_failed(self):
        """Test handling when collector failed but raise_collection_errors is False."""
        mock_rule = Mock()
        mock_rule.data_collector_exceptions = {}
        mock_rule.any_passed_data_collector = False

        mock_collector_class = Mock()
        mock_collector_class.__name__ = "TestCollector"
        mock_collector_class.raise_collection_errors = False

        host_exceptions = {"node1": "error1", "node2": "error2"}
        hosts_dict = {"node1": Mock(), "node2": Mock()}

        # Should not raise exception
        DataCollectorRunner.handle_collector_failures(
            mock_rule, mock_collector_class, host_exceptions, hosts_dict
        )

        assert "TestCollector" in mock_rule.data_collector_exceptions
        assert mock_rule.any_passed_data_collector is False

    def test_raise_collection_failed_on_all_hosts(self):
        """Test raising exception when collection failed on all hosts."""

        host_exceptions = {"node1": "error1", "node2": "error2"}
        hosts_dict = {"node1": Mock(), "node2": Mock()}

        with pytest.raises(UnExpectedSystemOutput) as exc_info:
            DataCollectorRunner.raise_collection_failed_on_all_hosts(
                "TestCollector", host_exceptions, hosts_dict
            )

        assert "TestCollector failed on all hosts" in str(exc_info.value)
        assert "node1, node2" in exc_info.value.ip

    def test_raise_collection_failed_on_all_hosts_no_raise_partial(self):
        """Test no exception when only partial failure."""
        host_exceptions = {"node1": "error1"}
        hosts_dict = {"node1": Mock(), "node2": Mock()}

        # Should not raise
        DataCollectorRunner.raise_collection_failed_on_all_hosts(
            "TestCollector", host_exceptions, hosts_dict
        )

    def test_raise_if_no_collector_passed_with_failures(self):
        """Test raising exception when no collectors passed."""

        mock_rule = Mock()
        mock_rule.any_passed_data_collector = False
        mock_rule.data_collector_exceptions = {
            "Collector1": {"node1": "error1"},
            "Collector2": {"node2": "error2"}
        }

        with pytest.raises(UnExpectedSystemOutput) as exc_info:
            DataCollectorRunner.raise_if_no_collector_passed(mock_rule)

        assert "All DataCollectors failed" in str(exc_info.value)
        assert "[Collector1]" in exc_info.value.output
        assert "[Collector2]" in exc_info.value.output

    def test_raise_if_no_collector_passed_without_exceptions(self):
        """Test raising exception when no collectors passed and no exceptions."""

        mock_rule = Mock()
        mock_rule.any_passed_data_collector = False
        mock_rule.data_collector_exceptions = {}

        with pytest.raises(UnExpectedSystemOutput) as exc_info:
            DataCollectorRunner.raise_if_no_collector_passed(mock_rule)

        assert "All DataCollectors failed" in str(exc_info.value)
        assert "No exception details available" in exc_info.value.output

    def test_raise_if_no_collector_passed_no_raise_when_passed(self):
        """Test no exception when at least one collector passed."""
        mock_rule = Mock()
        mock_rule.any_passed_data_collector = True
        mock_rule.data_collector_exceptions = {}

        # Should not raise
        DataCollectorRunner.raise_if_no_collector_passed(mock_rule)
