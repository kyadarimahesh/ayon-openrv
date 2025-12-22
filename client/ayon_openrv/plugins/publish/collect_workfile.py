import os
import pyblish.api

from ayon_core.pipeline import registered_host
from ayon_core.pipeline.workfile import save_next_version


class CollectWorkfile(pyblish.api.InstancePlugin):
    """Inject the current working file into context"""

    order = pyblish.api.CollectorOrder - 0.49
    label = "OpenRV Session Workfile"
    hosts = ["openrv"]
    families = ["workfile"]

    def process(self, instance):
        """Inject the current working file"""

        host = registered_host()
        current_file = host.get_current_workfile() or ""

        # Auto-save if no workfile exists
        if not current_file:
            self.log.info("No workfile detected. Auto-saving with AYON naming...")
            try:
                save_next_version()
                current_file = host.get_current_workfile() or ""
                self.log.info(f"Workfile auto-saved: {current_file}")
            except Exception as e:
                self.log.error(f"Failed to auto-save workfile: {str(e)}")

        folder, file = os.path.split(current_file) if current_file else ("", "")
        filename, ext = os.path.splitext(file)

        instance.context.data["currentFile"] = current_file

        if not current_file:
            self.log.error("No current filepath detected. "
                           "Make sure to save your OpenRV session")
            return

        instance.data["representations"] = [{
            "name": ext.lstrip("."),
            "ext": ext.lstrip("."),
            "files": file,
            "stagingDir": folder,
        }]
