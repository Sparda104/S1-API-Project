from collections.abc import Mapping, Sequence

def flatten(obj, parent_key='', sep='.'):
    items = {}
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            new_key = f'{parent_key}{sep}{k}' if parent_key else str(k)
            items.update(flatten(v, new_key, sep))
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for i, v in enumerate(obj, start=1):
            new_key = f'{parent_key}_{i}' if parent_key else str(i)
            items.update(flatten(v, new_key, sep))
    else:
        items[parent_key] = obj
    return items
