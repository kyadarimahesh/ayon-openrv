import os
import json
import sys
import importlib
import traceback

import rv.qtutils
from rv.rvtypes import MinorMode

from ayon_api import get_representations

from ayon_core.tools.utils import host_tools
from ayon_core.pipeline import (
    registered_host,
    install_host,
    discover_loader_plugins,
    load_container,
    get_current_project_name,
)
from ayon_openrv.api import OpenRVHost
from ayon_openrv.networking import LoadContainerHandler

from review_submitter.handlers.review_submission_handler import ReviewSubmissionHandler

# TODO (Critical) Remove this temporary hack to avoid clash with PyOpenColorIO
#   that is contained within AYON's venv
# Ensure PyOpenColorIO is loaded from RV instead of from AYON lib by
# moving all rv related paths to start of sys.path so RV libs are imported
# We consider the `/openrv` folder the root to  `/openrv/bin/rv` executable
rv_root = os.path.normpath(os.path.dirname(os.path.dirname(sys.executable)))
rv_paths = []
non_rv_paths = []
for path in sys.path:
    if os.path.normpath(path).startswith(rv_root):
        rv_paths.append(path)
    else:
        non_rv_paths.append(path)
sys.path[:] = rv_paths + non_rv_paths

import PyOpenColorIO  # noqa

importlib.reload(PyOpenColorIO)

from qtpy import QtCore


def install_host_in_ayon():
    host = OpenRVHost()
    install_host(host)


class AYONMenus(MinorMode):

    def __init__(self):
        MinorMode.__init__(self)

        menu_items = [
            ("Load...", self.load, "Ctrl+L", None),
            ("Publish...", self.publish, None, None),
            ("Manage...", self.scene_inventory, None, None),
            ("Library...", self.library, None, None),
            ("Activity Panel...", self.activity_panel, "Ctrl+A", None),
        ]

        if self._is_review_browser_available():
            menu_items.append(("Review Browser...", self.review_browser, "Ctrl+R", None))
        else:
            menu_items.append(("Collect Review Inputs", [
                ("First submission", self.first_submission, None, None),
                ("Resubmission", self.resubmission, None, None),
            ]))

        menu_items.extend([
            ("_", None),
            ("Work Files...", self.workfiles, None, None),
        ])

        self.init(
            name="py-ayon",
            globalBindings=None,
            overrideBindings=[
                ("ayon_load_container", on_ayon_load_container, "Loads an AYON representation into the session.")],
            menu=[("AYON", menu_items)],
            sortKey="source_setup",
            ordering=15
        )

    def _is_review_browser_available(self):
        """Check if Review Browser should be shown."""
        if not os.getenv("AYON_FOLDER_PATH"):
            try:
                import ayon_review_browser
                return True
            except ImportError:
                return False
        return False

    @property
    def _parent(self):
        return rv.qtutils.sessionWindow()

    def load(self, event):
        host_tools.show_loader(parent=self._parent, use_context=True)

    def review_browser(self, event):
        from ayon_review_browser import show_review_browser
        show_review_browser(parent=self._parent)

    def publish(self, event):
        host_tools.show_publisher(parent=self._parent, tab="publish")

    def workfiles(self, event):
        host_tools.show_workfiles(parent=self._parent)

    def scene_inventory(self, event):
        host_tools.show_scene_inventory(parent=self._parent)

    def library(self, event):
        host_tools.show_library_loader(parent=self._parent)

    def activity_panel(self, event):
        try:
            from ayon_activity_panel import show_activity_panel
            show_activity_panel(parent=self._parent, bind_rv_events=True)
        except ImportError:
            print("⚠️ Activity Panel addon not available")
        except Exception as e:
            print(f"❌ Failed to open Activity Panel: {e}")
            traceback.print_exc()

    def first_submission(self, event):
        ReviewSubmissionHandler.collect_review_inputs(self._parent, is_resubmission=False)

    def resubmission(self, event):
        ReviewSubmissionHandler.collect_review_inputs(self._parent, is_resubmission=True)


def data_loader():
    incoming_data_file = os.environ.get(
        "AYON_LOADER_REPRESENTATIONS", None
    )
    if incoming_data_file:
        with open(incoming_data_file, 'rb') as file:
            decoded_data = json.load(file)
        os.remove(incoming_data_file)
        load_data(dataset=decoded_data["representations"])
    else:
        print("No data for auto-loader")


def on_ayon_load_container(event):
    handler = LoadContainerHandler(event)
    handler.handle_event()


def load_data(dataset=None):
    project_name = get_current_project_name()
    available_loaders = discover_loader_plugins(project_name)
    Loader = next(loader for loader in available_loaders
                  if loader.__name__ == "FramesLoader")

    representations = get_representations(project_name,
                                          representation_ids=dataset)

    for representation in representations:
        load_container(Loader, representation)


# only add menu items if AYON_RV_NO_MENU is not set to 1
if os.getenv("AYON_RV_NO_MENU") != "1":
    def createMode():
        try:
            if not registered_host():
                install_host_in_ayon()
                data_loader()

            ayon_menus = AYONMenus()

            if ayon_menus._is_review_browser_available():
                ayon_menus.review_browser(None)

            # Maximize RV window
            rv.qtutils.sessionWindow().showMaximized()
            return ayon_menus
        except Exception as e:
            print(f"❌ FATAL ERROR in createMode: {e}")
            traceback.print_exc()
            raise
