import os
import json
import sys
import importlib

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
        self._activity_panel_dock = None  # Track existing panel

        menu_items = [
            ("Load...", self.load, None, None),
            ("Publish...", self.publish, None, None),
            ("Manage...", self.scene_inventory, None, None),
            ("Library...", self.library, None, None),
            ("Activity Panel...", self.activity_panel, "Ctrl+A", None),
        ]

        if self._is_review_browser_available():
            menu_items.append(("Review Browser...", self.review_browser, "Ctrl+R", None))
        else:
            menu_items.extend([
                ("Collect Review Inputs", [
                    ("First submission", self.first_submission, None, None),
                    ("Resubmission", self.resubmission, None, None),
                ]),
                ("Publish Review", self.publish_review, None, None)
            ])

        menu_items.extend([
            ("_", None),
            ("Work Files...", self.workfiles, None, None),
        ])

        self.init(
            name="py-ayon",
            globalBindings=None,
            overrideBindings=[("ayon_load_container", on_ayon_load_container, "Loads an AYON representation into the session.")],
            menu=[("AYON", menu_items)],
            sortKey="source_setup",
            ordering=15
        )

    def _is_review_browser_available(self):
        """Check if Review Browser should be shown."""
        # Only show Review Browser menu if no folder context (launched standalone)
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
        from ayon_review_browser import ReviewBrowser
        window = ReviewBrowser()
        window.showMaximized()

    def publish(self, event):
        host_tools.show_publisher(parent=self._parent,
                                  tab="publish")

    def workfiles(self, event):
        host_tools.show_workfiles(parent=self._parent)

    def scene_inventory(self, event):
        host_tools.show_scene_inventory(parent=self._parent)

    def library(self, event):
        host_tools.show_library_loader(parent=self._parent)

    def activity_panel(self, event):
        """Show Activity Panel (or bring to front if already exists)."""
        # Check if panel already exists
        if self._activity_panel_dock is not None:
            try:
                # Bring existing panel to front
                self._activity_panel_dock.show()
                self._activity_panel_dock.raise_()
                print("✅ Activity Panel already open, bringing to front")
                return
            except:
                # Panel was closed/deleted, create new one
                self._activity_panel_dock = None
        
        try:
            from ayon_activity_panel import ActivityPanel
            from ayon_core.pipeline import get_current_project_name

            project_name = get_current_project_name()
            panel = ActivityPanel(project_name=project_name, parent=self._parent)

            from qtpy.QtWidgets import QDockWidget
            from qtpy.QtCore import Qt

            dock = QDockWidget("Activity Panel", self._parent)
            dock.setWidget(panel)
            self._parent.addDockWidget(Qt.RightDockWidgetArea, dock)
            dock.show()
            
            # Store reference
            self._activity_panel_dock = dock

            # Load statuses
            import ayon_api
            if project_name:
                project_data = ayon_api.get_project(project_name)
                statuses = project_data.get('statuses', {})

                # Handle both dict and list formats
                if isinstance(statuses, dict):
                    status_list = [
                        {'value': name, 'color': data.get('color', '#ffffff')}
                        for name, data in statuses.items()
                    ]
                elif isinstance(statuses, list):
                    status_list = [
                        {'value': s.get('name', s.get('value', '')),
                         'color': s.get('color', '#ffffff')}
                        for s in statuses
                    ]
                else:
                    status_list = []

                panel.set_available_statuses(status_list)

        except ImportError:
            print("⚠️ Activity Panel addon not available")
        except Exception as e:
            print(f"❌ Failed to open Activity Panel: {e}")
            import traceback
            traceback.print_exc()
    def first_submission(self, event):
        """First submission - collect plates, EditOT, and current render versions"""
        from review_submitter.handlers.review_submission_handler import ReviewSubmissionHandler
        ReviewSubmissionHandler.collect_review_inputs(self._parent, is_resubmission=False)

    def resubmission(self, event):
        """Resubmission - collect only current render versions with previous comparison"""
        from review_submitter.handlers.review_submission_handler import ReviewSubmissionHandler
        ReviewSubmissionHandler.collect_review_inputs(self._parent, is_resubmission=True)

    def publish_review(self, event):
        """Auto-publish then show review dialog"""
        from review_submitter.handlers.review_submission_handler import ReviewSubmissionHandler

        host_tools.show_publisher(parent=self._parent, tab="publish")
        QtCore.QTimer.singleShot(1000, lambda: ReviewSubmissionHandler.trigger_publish_and_review(self._parent))


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
        # This function triggers for each RV session window being opened, for
        # example when using File > New Session this will trigger again. As such
        # we only want to trigger the startup install when the host is not
        # registered yet.
        if not registered_host():
            install_host_in_ayon()
            data_loader()

        ayon_menus = AYONMenus()

        # Auto-open Activity Panel
        ayon_menus.activity_panel(None)

        # Auto-open Review Browser only if addon is available
        if ayon_menus._is_review_browser_available():
            ayon_menus.review_browser(None)

        # Maximize RV window
        rv.qtutils.sessionWindow().showMaximized()
        return ayon_menus
