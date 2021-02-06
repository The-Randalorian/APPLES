import os

from . import apm


extension_handlers = {
    ".apm": apm
}


def install(plugin_remote_url, repository):
    extension = os.path.splitext(plugin_remote_url)[-1]
    extension_handler = extension_handlers.get(extension, extension_handlers[".apm"])
    extension_handler.install(plugin_remote_url, repository)
