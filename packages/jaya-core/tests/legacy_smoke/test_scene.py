import sys

import pytest

pytestmark = pytest.mark.manual

sys.path.insert(0, ".")

from jaya_core.os_kernel.ui_spec import (  # noqa: E402
    SceneGraph,
    create_button,
    create_label,
    create_panel,
    create_window,
)

scene = SceneGraph(
    name="Test Dialog",
    description="Test dialog for compiler",
    root=create_window(
        title="Test",
        width="400px",
        height="300px",
        children=[
            create_panel(
                layout="flex_col",
                children=[
                    create_label("Hello World"),
                    create_button(label="Click Me", on_click="jaya:run_task"),
                ],
            ),
        ],
    ),
)
print("Scene created successfully")
print(f"Scene name: {scene.name}")
print(f"Root type: {scene.root.type}")
