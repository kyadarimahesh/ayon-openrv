import pyblish.api

from ayon_core.pipeline.publish import PublishValidationError


class ValidateCurrentWorkFile(pyblish.api.InstancePlugin):
    """Auto-save workfile if not saved, then validate."""

    label = "Validate Workfile"
    order = pyblish.api.ValidatorOrder - 0.1
    hosts = ["openrv"]
    families = ["workfile", "review"]

    def process(self, instance):
        host = registered_host()
        current_file = host.get_current_workfile()

        # If no workfile, save it now for any publish type
        if not current_file:
            try:
                save_next_version()
                current_file = host.get_current_workfile()
                instance.context.data["currentFile"] = current_file
                instance.context.data["workfileWasCreated"] = True
            except Exception as e:
                raise PublishValidationError(f"Failed to save workfile: {str(e)}")

        if not current_file:
            raise PublishValidationError("No workfile available to publish.")

