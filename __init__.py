#!/usr/bin/env python3

# APPLES - Automatic Python Plugin Loading & Executing Script

# Version 0.2.0

import os              # Library used for accessing basic os features.
# import sys             # Library used for accessing core system features
import importlib       # Library used for dynamically loading plugins.
# import configparser    # Library used for reading library information
import json             # Library used for reading plugin information.
# import traceback       # Library used for getting error information
# import urllib.request  # Library used for downloading files
import copy            # Library used for copying info for ordering
import logging          # Library used for logging.
from types import ModuleType

_logger = logging.getLogger(f"{__name__}")
_plugins: ModuleType


APPLE_DIRECTORY = os.path.dirname(os.path.realpath(__file__))
PLUGIN_DIRECTORY = APPLE_DIRECTORY + os.sep + "plugins"
COLLECTION_DIRECTORY = APPLE_DIRECTORY + os.sep + "collections"


class ApplesException(Exception):  # Create a custom exception for my purposes
    pass  # it does nothing special


class ApplesDirectiveException(ApplesException):
    pass


class ApplesExit(ApplesException):
    def __init__(self, code: int, message: str = ""):
        self.code = code
        self.message = message


def _make_folder(path):
    try:
        os.makedirs(path)
    except FileExistsError:
        pass


def _setup_directories():
    _make_folder(PLUGIN_DIRECTORY)
    _make_folder(COLLECTION_DIRECTORY)
    with open(PLUGIN_DIRECTORY + os.sep + "__init__.py", "w") as initfile:
        initfile.write('''#!/usr/bin/env python3
import os
import typing
import logging

APPLE_DIRECTORY = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
PLUGIN_DIRECTORY = APPLE_DIRECTORY + os.sep + "plugins"
COLLECTION_DIRECTORY = APPLE_DIRECTORY + os.sep + "collections"

ApplesExit: typing.NewType('ApplesExit', Exception)

_logger = logging.getLogger(f"{__name__}")

plugins = {}
services = {}
plugin_data = {}


def setup():
    _logger.warn("No setup function provided by any plugins.")
    
    
def loop():
    _logger.critical("No loop function provided by any plugins.")
    raise Exception("No loop function provided by any plugins.")
    
def cleanup():
    _logger.warn("No cleanup function provided by any plugins.")
''')


def _apm_handler(source_file, manifests):
    _logger.info(f"Loading manifest {source_file}.")
    with open(source_file, "r") as plugin_manifest_file:
        plugin_manifest = json.load(plugin_manifest_file)
        plugin_manifest = _apm_json_handlers[plugin_manifest["format"]](plugin_manifest)
        manifests.append(plugin_manifest)
    plugin_human_name = plugin_manifest["name"]
    _logger.info(f"Loaded manifest for {plugin_human_name}. ({source_file})")


def _parse_apm_json_0_1_0(plugin_manifest):
    plugin_human_name = plugin_manifest.get("human-name", None)
    if plugin_human_name is None:
        plugin_human_name = plugin_manifest["name"]
        _logger.warning(f"No human name found for {plugin_human_name}. Using module name.")
    _logger.debug(f"Detected manifest format 0.1.0 for {plugin_human_name}.")
    p_m = {
        "human-name": plugin_human_name,
        "requirements": [],
        "load-directives": [],
        "files": [],
    }
    p_m.update(plugin_manifest)
    return p_m


_apm_json_handlers = {
    "0.1.0": _parse_apm_json_0_1_0
}

_file_handlers = {
    ".apm": _apm_handler,
}


def _load_plugin_manifests(plugin_data):
    manifests = []

    _logger.info("Loading plugin manifests.")
    for filename in os.listdir(PLUGIN_DIRECTORY):
        for f_type in _file_handlers.keys():
            if filename.endswith(f_type): 
                _file_handlers[f_type](os.path.join(PLUGIN_DIRECTORY, filename), manifests)
    _logger.info("Loaded plugin manifests.")

    for manifest in manifests:
        plugin_entry = plugin_data[manifest["name"]] = manifest
        plugin_entry["loaded"] = False
        plugin_entry["can-load"] = False


def _resolve_plugin_name(plugin_name, plugin_data):
    if plugin_name.startswith("$"):
        for plugin_entry in plugin_data.values():
            if plugin_entry["service"] == plugin_name[1:]:
                yield plugin_entry["name"]
    else:
        yield plugin_name


def _directive_load_before(directive, plugin_entry, plugin_data, _):
    module_name_formula = directive["module"]
    module_names = _resolve_plugin_name(module_name_formula, plugin_data)
    plugin_name = plugin_entry["name"]
    for module_name in module_names:
        module_entry = plugin_data[module_name]
        module_human_name = module_entry["human-name"]
        if not plugin_entry["loaded"]:
            _logger.debug(f"Prevented {module_human_name} from loading this cycle. "
                          f"({plugin_name}.load-before.{module_name_formula})")
            plugin_data[module_name]["can-load"] = False


def _directive_load_after(directive, plugin_entry, plugin_data, _):
    module_name_formula = directive["module"]
    module_names = _resolve_plugin_name(module_name_formula, plugin_data)
    plugin_name = plugin_entry["name"]
    plugin_human_name = plugin_entry["human-name"]
    for module_name in module_names:
        if not plugin_data[module_name]["loaded"]:
            _logger.debug(f"Prevented {plugin_human_name} from loading this cycle. "
                          f"({plugin_name}.load-after.{module_name_formula})")
            plugin_entry["can-load"] = False


def _directive_load_deny(directive, plugin_entry, plugin_data, _):
    module_name_formula = directive["module"]
    module_names = _resolve_plugin_name(module_name_formula, plugin_data)
    plugin_name = plugin_entry["name"]
    for module_name in module_names:
        module_entry = plugin_data[module_name]
        module_human_name = module_entry["human-name"]
        if module_name == plugin_name:
            continue
        if plugin_data.get(module_name, None) is not None:
            _logger.critical(f"Found denied plugin {module_human_name}. "
                             f"({plugin_name}.load-after.{module_name_formula})")
            raise ApplesDirectiveException("Denied plugin")


def _directive_run_after_load(directive, plugin_entry, plugin_data, plugins):
    executed = directive.setdefault("executed", False)
    method_name = directive["method"]
    module_name_formula = directive["module"]
    module_names = _resolve_plugin_name(module_name_formula, plugin_data)
    plugin_name = plugin_entry["name"]
    plugin_human_name = plugin_entry["human-name"]
    if not executed:
        for module_name in module_names:
            module_entry = plugin_data[module_name]
            if not module_entry["loaded"]:
                _logger.debug(f"Cannot run {method_name} for {plugin_human_name} yet. "
                              f"Required module {module_name} is not loaded. "
                              f"({plugin_name}.run-after-load.{module_name_formula})")
                return
        if plugin_entry["loaded"]:
            directive["executed"] = True
            getattr(plugins.plugins[plugin_name], method_name)()
            _logger.debug(f"Ran {method_name} for {plugin_human_name}. "
                          f"({plugin_name}.run-after-load.{module_name_formula})")
        else:
            _logger.debug(f"Did not run {method_name} for {plugin_human_name} because the module is not loaded. "
                          f"({plugin_name}.run-after-load.{module_name_formula})")


_load_directives = {
    "load-after": _directive_load_after,
    "load-before": _directive_load_before,
    "load-deny": _directive_load_deny,
    "run-after-load": _directive_run_after_load
}


def _load_plugin(plugin_entry, plugins):
    plugin_name = plugin_entry["name"]
    plugin_human_name = plugin_entry["human-name"]
    plugin_service = plugin_entry["name"]
    _logger.info(f"Loading {plugin_human_name}.")
    plugin_module = importlib.import_module(f".plugins.{plugin_name}", package=__package__)
    _logger.info(f"Loaded {plugin_human_name}.")
    getattr(plugins, "plugins", {})[plugin_name] = plugin_module
    getattr(plugins, "services", {}).setdefault(plugin_service, []).append(plugin_module)
    getattr(plugins, "plugin_data", {})[plugin_name] = copy.deepcopy(plugin_entry)
    plugin_entry["loaded"] = True


def _load_plugins(plugin_data):
    # Invalidate all cached modules
    _logger.debug("Invalidating caches.")
    importlib.invalidate_caches()
    plugins = importlib.import_module(".plugins", package=__package__)
    plugins.ApplesExit = ApplesExit

    _logger.info("Loading plugins.")
    while True:
        # Reset all can-load flags
        for plugin_entry in plugin_data.values():
            plugin_entry["can-load"] = True

        # Apply load directives
        for plugin_entry in plugin_data.values():
            for directive in plugin_entry["load-directives"]:
                _load_directives[directive["directive"]](directive, plugin_entry, plugin_data, plugins)

        # Load any plugins it can
        loaded_any = False  # Set initial values for flags to signal if any or all
        loaded_all = True  # plugins were loaded
        for plugin_entry in plugin_data.values():
            if not plugin_entry["loaded"]:
                loaded_all = False
                if plugin_entry["can-load"]:
                    loaded_any = True
                    _load_plugin(plugin_entry, plugins)

        # Break if all plugins are loaded
        if loaded_all:
            break

        # Raise an exception if the system is stuck.
        if not loaded_any:
            raise ApplesDirectiveException("Plugins are being blocked from loading (Probably by directives).")
    _logger.info("All plugins loaded.")
    return plugins


def init():
    global _plugins
    plugin_data = {}
    _setup_directories()
    _load_plugin_manifests(plugin_data)
    _plugins = plugins = _load_plugins(plugin_data)
    return plugins


def setup(plugins=None):
    if plugins is None:
        plugins = _plugins
    plugins.setup()


def loop(plugins=None):
    if plugins is None:
        plugins = _plugins
    plugins.loop()


def cleanup(plugins=None):
    if plugins is None:
        plugins = _plugins
    plugins.cleanup()