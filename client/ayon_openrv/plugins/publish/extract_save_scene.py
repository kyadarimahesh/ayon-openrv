import pyblish.api

from ayon_core.pipeline import registered_host, KnownPublishError
from ayon_core.pipeline.workfile import save_next_version


class ExtractSaveScene(pyblish.api.ContextPlugin):
    """Save scene before extraction."""

    order = pyblish.api.ExtractorOrder - 0.48
    label = "Extract Save Scene"
    hosts = ["openrv"]

    def process(self, context):
        host = registered_host()

        current_file_name = host.get_current_workfile()
        self.log.info("current_file_name::{}".format(current_file_name))
        if not current_file_name:
            raise KnownPublishError("No workfile available!")

        # Only save if workfile wasn't just created
        if not context.data.get("workfileWasCreated"):
            print(f"Saving existing workfile: {current_file_name}")
            host.save_workfile(current_file_name)
        else:
            print("Skipping save - workfile was just created in validator")