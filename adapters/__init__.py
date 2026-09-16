import pkgutil
import importlib

from adapters.base import get_adapter, all_sources, REGISTRY

# Adapters that failed to load: file name -> error message
FAILED_ADAPTERS = {}

# Import every module in this folder so each adapter class
# registers itself. Adding a source = adding a file. That's it.
# If one file is broken, skip it and keep loading the others.
for _, module_name, _ in pkgutil.iter_modules(__path__):
    if module_name == "base":
        continue
    try:
        importlib.import_module(f"adapters.{module_name}")
    except Exception as e:
        FAILED_ADAPTERS[module_name] = str(e)
        print(f"[adapters] WARNING: skipped '{module_name}': {e}")
