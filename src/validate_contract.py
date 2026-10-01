"""Validator for DNA-Lang Evolver Contracts against formal JSON Schema."""
import json
import os
from typing import Any, Dict, List, Optional, Tuple, Union
import jsonschema
import yaml


DEFAULT_SCHEMA_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../schemas/dna.evolver_contract.v1.schema.json")
)


def load_contract(source: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Load a contract from a YAML/JSON string or file path, or return dict directly."""
    if isinstance(source, dict):
        return source
    if os.path.exists(source):
        with open(source, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = source

    try:
        # YAML is a superset of JSON, handles both
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            raise ValueError(f"Contract content must parse to a dictionary, got {type(data).__name__}")
        return data
    except Exception as e:
        raise ValueError(f"Failed to parse contract: {e}") from e


def load_schema(schema_path: Optional[str] = None) -> Dict[str, Any]:
    """Load the JSON schema from file."""
    path = schema_path or DEFAULT_SCHEMA_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(f"Contract schema file not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_contract(
    contract_data: Union[str, Dict[str, Any]],
    schema_path: Optional[str] = None
) -> Tuple[bool, List[str]]:
    """Validate a contract data structure against the formal JSON schema.
    
    Returns:
        (is_valid, list_of_error_messages)
    """
    try:
        contract = load_contract(contract_data)
    except Exception as e:
        return False, [f"Contract loading error: {str(e)}"]

    try:
        schema = load_schema(schema_path)
    except Exception as e:
        return False, [f"Schema loading error: {str(e)}"]

    validator_cls = jsonschema.validators.validator_for(schema)
    validator = validator_cls(schema)

    errors = []
    for error in validator.iter_errors(contract):
        path = " -> ".join(str(p) for p in error.path) if error.path else "root"
        errors.append(f"[{path}] {error.message}")

    return (len(errors) == 0, errors)
