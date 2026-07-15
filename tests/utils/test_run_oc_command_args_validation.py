"""
Test that all run_oc_command args in source code pass validation.

This test discovers all OrchestratorRule and OrchestratorDataCollector subclasses,
instantiates each with a mock operator, and calls their methods.
The mock intercepts the ACTUAL resolved args (including f-strings) and validates
them against _validate_args_safe().

This catches injection attempts that static linters miss, because the code is
actually executed and f-strings are resolved to their real values.
"""

import importlib
import inspect
import pkgutil
import types
import typing
from unittest.mock import MagicMock

import pytest

import in_cluster_checks.rules as rules_package
from in_cluster_checks.core.operations import DataCollector
from in_cluster_checks.core.rule import OrchestratorRule
from in_cluster_checks.utils.oc_api_utils import OcApiUtils


class MockOperator:
    """Minimal mock operator for OcApiUtils instantiation."""

    def _add_cmd_to_log(self, cmd):
        pass

    def get_host_ip(self):
        return "localhost"


class ApiObjectMock(str):
    """str subclass that acts as a mock API object.

    Inherits __str__, __format__, __eq__, __hash__, __bool__ from str.
    Only defines attribute access, calling, iteration, and dict-like methods.
    """

    def __new__(cls, name="mock-resource"):
        return str.__new__(cls, name)

    def __getattr__(self, attr):
        return ApiObjectMock(self)

    def __call__(self, *args, **kwargs):
        return ApiObjectMock(self)

    def __getitem__(self, key):
        return ApiObjectMock(self)

    def __iter__(self):
        return iter([ApiObjectMock(self)])

    def get(self, key, default=None):
        return ApiObjectMock(self)

    def items(self):
        return [("mock-key", ApiObjectMock(self))]

    def values(self):
        return [ApiObjectMock(self)]

    def keys(self):
        return ["mock-key"]


def _make_mock_api_object(name="mock-resource"):
    """Create a mock that behaves like an openshift_client APIObject.

    Uses ApiObjectMock so any attribute accessed in f-strings automatically
    produces a valid string. No explicit attribute setup needed — the mock
    handles arbitrary nesting dynamically.
    """
    return ApiObjectMock(name)


def _import_all_rule_modules():
    """Import all modules under in_cluster_checks.rules to discover subclasses."""
    package_path = rules_package.__path__
    for _, module_name, _ in pkgutil.walk_packages(package_path, prefix=rules_package.__name__ + "."):
        try:
            importlib.import_module(module_name)
        except Exception:
            continue


def _get_all_subclasses(base):
    """Recursively collect all subclasses of a base class."""
    result = []
    for cls in base.__subclasses__():
        result.append(cls)
        result.extend(_get_all_subclasses(cls))
    return result


def _class_uses_run_oc_command(cls):
    """Check if class or any non-framework parent uses run_oc_command.

    Walks the MRO so child classes that inherit run_oc_command calls from
    intermediate parents (e.g. WhereaboutsBaseRule) are discovered.
    """
    for klass in cls.__mro__:
        if klass in (object, OrchestratorRule, DataCollector):
            continue
        if klass.__module__.startswith("in_cluster_checks.core"):
            continue
        try:
            source = inspect.getsource(klass)
        except (TypeError, OSError):
            continue
        if "run_oc_command" in source:
            return True
    return False


def _find_classes_with_run_oc_command():
    """Find all OrchestratorRule and DataCollector subclasses that use run_oc_command."""
    _import_all_rule_modules()

    classes = []
    for base_class in (OrchestratorRule, DataCollector):
        for cls in _get_all_subclasses(base_class):
            if not hasattr(cls, "unique_name") or not hasattr(cls, "title"):
                continue
            if _class_uses_run_oc_command(cls):
                classes.append(cls)

    return classes


def _create_mock_instance(cls):
    """Create an instance of a rule/collector class with mock operator.

    Tries proper __init__ to preserve rule-specific instance attributes,
    falls back to __new__ if __init__ fails with mocks.
    """
    mock_executor = MagicMock()
    mock_executor.node_name = "test-node"
    mock_executor.ip = "192.168.1.10"
    mock_executor.host_name = "test-node"

    try:
        if issubclass(cls, OrchestratorRule):
            instance = cls(host_executor=mock_executor, node_executors=None)
        else:
            instance = cls(host_executor=mock_executor)
    except Exception:
        instance = cls.__new__(cls)
        instance.logger = MagicMock()
        instance._host_executor = mock_executor
        instance.node_name = "test-node"

    instance.oc_api = OcApiUtils(MockOperator())

    return instance


def _return_type_contains(return_type, target):
    """Check if a return type annotation contains a target type, handling Unions and generics."""
    if return_type is target:
        return True
    origin = typing.get_origin(return_type)
    if origin is target:
        return True
    if origin is types.UnionType or origin is typing.Union:
        return any(_return_type_contains(arg, target) for arg in typing.get_args(return_type))
    return False


def _mock_oc_api_methods(instance, mock_obj):
    """Dynamically mock all public OcApiUtils methods based on return type annotations.

    Inspects OcApiUtils for all public methods, skips run_oc_command (which is
    replaced with a capturing version by the caller), and picks a mock return
    value from the method's return type annotation:
      list  -> [mock_obj]    (so loop bodies execute)
      dict  -> {"items": []} (so .get("items", []) works)
      tuple -> (0, "{}", "") (rc, stdout, stderr)
      str   -> "mock-value"
      other -> mock_obj      (ApiObjectMock, valid for f-strings)
    """
    for name, method in inspect.getmembers(OcApiUtils, predicate=inspect.isfunction):
        if name.startswith("_") or name == "run_oc_command":
            continue

        try:
            hints = typing.get_type_hints(method)
        except Exception:
            hints = {}

        return_type = hints.get("return")
        if return_type is None:
            mock_return = mock_obj
        elif _return_type_contains(return_type, list):
            mock_return = [mock_obj]
        elif _return_type_contains(return_type, dict):
            mock_return = {"items": []}
        elif _return_type_contains(return_type, tuple):
            mock_return = (0, "{}", "")
        elif _return_type_contains(return_type, str):
            mock_return = "mock-value"
        else:
            mock_return = mock_obj

        setattr(instance.oc_api, name, MagicMock(return_value=mock_return))


def _collect_run_oc_command_args(instance):
    """
    Call all methods on the instance and capture args passed to run_oc_command.

    Args are converted to strings via str() so that ApiObjectMock instances
    resolve to their name, matching how f-string interpolation works in real code.

    Returns:
        List of (command, args_list) tuples
    """
    captured_calls = []

    def capturing_run_oc_command(command, args, **kwargs):
        captured_calls.append((command, [str(a) for a in args]))
        return (0, "{}", "")

    mock_obj = _make_mock_api_object()
    _mock_oc_api_methods(instance, mock_obj)
    instance.oc_api.run_oc_command = capturing_run_oc_command
    instance.run_data_collector = MagicMock(return_value=mock_obj)

    for name, method in inspect.getmembers(instance, predicate=inspect.ismethod):
        if name == "__init__":
            continue

        sig = inspect.signature(method)
        params = [
            p for p in sig.parameters.values()
            if p.name != "self" and p.default is inspect.Parameter.empty
        ]
        if not params:
            try:
                method()
            except Exception:
                pass
        else:
            mock_args = [_make_mock_api_object() for _ in params]
            try:
                method(*mock_args)
            except Exception:
                pass

    return captured_calls


_classes_with_run_oc = _find_classes_with_run_oc_command()


@pytest.mark.parametrize(
    "rule_class",
    _classes_with_run_oc,
    ids=[cls.__name__ for cls in _classes_with_run_oc],
)
def test_run_oc_command_args_are_safe(rule_class):
    """Validate that all run_oc_command args in a rule class pass _validate_args_safe()."""
    instance = _create_mock_instance(rule_class)
    captured_calls = _collect_run_oc_command_args(instance)

    oc_api = OcApiUtils(MockOperator())
    errors = []

    for command, args in captured_calls:
        if not oc_api._validate_args_safe(args):
            errors.append(f"oc {command} {args}")

    assert not errors, (
        f"Unsafe run_oc_command args found in {rule_class.__name__}:\n"
        + "\n".join(f"  - {e}" for e in errors)
    )
