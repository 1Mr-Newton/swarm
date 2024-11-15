import inspect
from datetime import datetime
from typing import Union, List, Optional, get_origin, get_args, Dict, Any


def debug_print(debug: bool, *args: str) -> None:
    if not debug:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = " ".join(map(str, args))
    print(f"\033[97m[\033[90m{timestamp}\033[97m]\033[90m {message}\033[0m")


def merge_fields(target, source):
    for key, value in source.items():
        if isinstance(value, str):
            target[key] += value
        elif value is not None and isinstance(value, dict):
            merge_fields(target[key], value)


def merge_chunk(final_response: dict, delta: dict) -> None:
    delta.pop("role", None)
    merge_fields(final_response, delta)

    tool_calls = delta.get("tool_calls")
    if tool_calls and len(tool_calls) > 0:
        index = tool_calls[0].pop("index")
        merge_fields(final_response["tool_calls"][index], tool_calls[0])

 

def function_to_json(func) -> dict:
    """
    Converts a Python function into a JSON-serializable dictionary
    that describes the function's signature, including its name,
    description, and parameters.

    Args:
        func: The function to be converted.

    Returns:
        A dictionary representing the function's signature in JSON format.
    """
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        type(None): "null",
    }

    def parse_type(annotation):
        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is Union:
            # Handle Optional[...] which is Union[..., None]
            if type(None) in args:
                non_none_types = [arg for arg in args if arg is not type(None)]
                if len(non_none_types) == 1:
                    parsed = parse_type(non_none_types[0])
                    if isinstance(parsed, dict) and "type" in parsed:
                        parsed["nullable"] = True
                        return parsed
            # General Union types can be represented as multiple types
            types = []
            items = None
            for arg in args:
                parsed = parse_type(arg)
                if isinstance(parsed, dict):
                    types.append(parsed.get("type", "string"))
                    if parsed.get("type") == "array" and "items" in parsed:
                        items = parsed["items"]
                else:
                    types.append("string")
            # Remove duplicates
            types = list(set(types))
            schema = {"type": types}
            if items:
                schema["items"] = items
            return schema

        elif origin in [list, List]:
            items_type = "string"  # Default to string if not specified
            if args:
                parsed_items = parse_type(args[0])
                if isinstance(parsed_items, dict):
                    items_type = parsed_items.get("type", "string")
            return {"type": "array", "items": {"type": items_type}}

        elif origin in [dict, Dict]:
            additional_properties = {
                "type": "string"
            }  # Default to string if not specified
            if len(args) == 2:
                key_type, value_type = args
                # Typically, JSON object keys are strings
                # But we'll parse value_type for the type
                parsed_value = parse_type(value_type)
                if isinstance(parsed_value, dict):
                    additional_properties = parsed_value
            return {"type": "object", "additionalProperties": additional_properties}

        else:
            return {"type": type_map.get(annotation, "string")}

    try:
        signature = inspect.signature(func)
    except ValueError as e:
        raise ValueError(
            f"Failed to get signature for function {func.__name__}: {str(e)}"
        )

    parameters = {}
    for param in signature.parameters.values():
        if param.annotation == inspect.Parameter.empty:
            param_type = {"type": "string"}  # Default type if no annotation
        else:
            param_type = parse_type(param.annotation)
        parameters[param.name] = param_type

    required = [
        param.name
        for param in signature.parameters.values()
        if param.default == inspect.Parameter.empty
    ]

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": func.__doc__ or "",
            "parameters": {
                "type": "object",
                "properties": parameters,
                "required": required,
            },
        },
    }
