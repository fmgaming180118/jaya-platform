"""Phase 3C — Intent to UI Pipeline (brain_v2).

This module bridges natural language intent to dynamic UI generation.
It uses the IntentEngine to understand user intent and generates
SceneGraph specifications that can be compiled into runnable features.

This is the core of Phase 3C: Dynamic UI Generation.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from jaya_core.brain_v2.engine.intent_engine import IntentEngine
from jaya_core.os_kernel.feature_bridge import JayaBridge
from jaya_core.os_kernel.ui_spec import (
    LayoutType,
    SceneGraph,
    create_button,
    create_label,
    create_panel,
    create_text_input,
    create_window,
)


@dataclass
class IntentMatch:
    """Result of intent matching."""
    intent_type: str
    confidence: float
    parameters: Dict[str, Any] = field(default_factory=dict)
    suggested_ui: Optional[str] = None  # UI template name


@dataclass
class UITemplate:
    """Pre-defined UI template for common intent types."""
    name: str
    description: str
    intent_patterns: List[str]  # Patterns that trigger this template
    required_params: List[str]
    builder: Callable[..., SceneGraph]  # Function that builds the SceneGraph
    optional_params: List[str] = field(default_factory=list)


class IntentToUIPipeline:
    """Pipeline: Natural Language Intent → SceneGraph → Feature."""

    def __init__(
        self,
        bridge: JayaBridge,
        intent_engine: Optional[IntentEngine] = None,
        templates_dir: Optional[Path] = None,
    ):
        self.bridge = bridge
        self.intent_engine = intent_engine or IntentEngine()
        self.templates: Dict[str, UITemplate] = {}
        self._register_builtin_templates()

        if templates_dir:
            self._load_custom_templates(templates_dir)

    def _register_builtin_templates(self) -> None:
        """Register built-in UI templates for common intents."""

        # Login Dialog Template
        self.templates["login_dialog"] = UITemplate(
            name="login_dialog",
            description="User authentication dialog with username/password",
            intent_patterns=[
                "login", "sign in", "signin", "authenticate", "log in",
                "show login", "create login dialog", "auth dialog"
            ],
            required_params=["title"],
            optional_params=["width", "height", "show_forgot_password", "remember_me"],
            builder=self._build_login_dialog,
        )

        # Dashboard Template
        self.templates["dashboard"] = UITemplate(
            name="dashboard",
            description="Main dashboard with metrics, charts, and quick actions",
            intent_patterns=[
                "dashboard", "show dashboard", "create dashboard",
                "main view", "overview", "admin panel", "control panel"
            ],
            required_params=["title"],
            optional_params=["metrics", "charts", "quick_actions", "sidebar"],
            builder=self._build_dashboard,
        )

        # Settings Dialog Template
        self.templates["settings_dialog"] = UITemplate(
            name="settings_dialog",
            description="Application settings and preferences dialog",
            intent_patterns=[
                "settings", "preferences", "options", "configure",
                "show settings", "open settings", "settings dialog"
            ],
            required_params=["title"],
            optional_params=["sections", "tabs"],
            builder=self._build_settings_dialog,
        )

        # File Explorer Template
        self.templates["file_explorer"] = UITemplate(
            name="file_explorer",
            description="File system browser with navigation and actions",
            intent_patterns=[
                "file explorer", "file manager", "browse files",
                "open files", "file browser", "directory view"
            ],
            required_params=["title", "root_path"],
            optional_params=["show_hidden", "multi_select", "file_filters"],
            builder=self._build_file_explorer,
        )

        # Chat Interface Template
        self.templates["chat_interface"] = UITemplate(
            name="chat_interface",
            description="Chat/conversation interface with message history",
            intent_patterns=[
                "chat", "conversation", "messaging", "talk to",
                "chat interface", "message window", "chat window"
            ],
            required_params=["title"],
            optional_params=["placeholder", "send_button_text", "show_timestamps"],
            builder=self._build_chat_interface,
        )

        # Confirmation Dialog Template
        self.templates["confirm_dialog"] = UITemplate(
            name="confirm_dialog",
            description="Simple confirmation dialog with yes/no",
            intent_patterns=[
                "confirm", "are you sure", "confirmation",
                "ask confirmation", "show confirm", "yes no dialog"
            ],
            required_params=["title", "message"],
            optional_params=["confirm_text", "cancel_text", "variant"],
            builder=self._build_confirm_dialog,
        )

        # Progress Dialog Template
        self.templates["progress_dialog"] = UITemplate(
            name="progress_dialog",
            description="Progress indicator with optional cancel",
            intent_patterns=[
                "progress", "loading", "working", "please wait",
                "show progress", "progress bar", "loading dialog"
            ],
            required_params=["title", "message"],
            optional_params=["show_percentage", "cancellable", "indeterminate"],
            builder=self._build_progress_dialog,
        )

        # List/Table View Template
        self.templates["list_view"] = UITemplate(
            name="list_view",
            description="Data list or table with sorting and actions",
            intent_patterns=[
                "list", "table", "show list", "data table",
                "grid view", "item list", "records"
            ],
            required_params=["title", "columns"],
            optional_params=["data", "sortable", "selectable", "actions"],
            builder=self._build_list_view,
        )

        # Form Template
        self.templates["form"] = UITemplate(
            name="form",
            description="Data entry form with validation",
            intent_patterns=[
                "form", "create form", "data entry", "input form",
                "registration form", "contact form", "survey"
            ],
            required_params=["title", "fields"],
            optional_params=["submit_text", "cancel_text", "validation"],
            builder=self._build_form,
        )

        # Generic Dialog Template (fallback)
        self.templates["generic_dialog"] = UITemplate(
            name="generic_dialog",
            description="Generic dialog with custom content",
            intent_patterns=[
                "dialog", "popup", "modal", "window", "show dialog"
            ],
            required_params=["title"],
            optional_params=["content", "buttons", "size"],
            builder=self._build_generic_dialog,
        )

    def _load_custom_templates(self, templates_dir: Path) -> None:
        """Load custom templates from JSON files."""
        for template_file in templates_dir.glob("*.json"):
            try:
                with open(template_file, "r", encoding="utf-8") as f:
                    json.load(f)
                # Custom template loading would go here
                # For now, just log
                print(f"Loaded custom template: {template_file.name}")
            except Exception as e:
                print(f"Failed to load template {template_file}: {e}")

    def _compact_children(self, children: List[Any]) -> List[Any]:
        """Remove empty child slots from builder lists."""
        return [child for child in children if child is not None]

    # ============================================================
    # Template Builders
    # ============================================================

    def _build_login_dialog(
        self,
        title: str = "Login",
        width: str = "400px",
        height: str = "350px",
        show_forgot_password: bool = True,
        remember_me: bool = True,
        **kwargs
    ) -> SceneGraph:
        """Build a login dialog SceneGraph."""
        return SceneGraph(
            name="Login Dialog",
            description="User authentication dialog",
            root=create_window(
                title=title,
                width=width,
                height=height,
                children=[
                    create_panel(
                        layout=LayoutType.FLEX_COL,
                        style={"padding": "24px", "gap": "16px"},
                        children=self._compact_children([
                            create_label(
                                "Welcome to JAYA",
                                style={"font_size": "24px", "font_weight": "600", "margin_bottom": "24px"}
                            ),
                            create_text_input(
                                placeholder="Username or Email",
                                on_change="jaya:update_state",
                            ),
                            create_text_input(
                                placeholder="Password",
                                value="",
                                on_change="jaya:update_state",
                            ),
                            create_button(
                                label="Sign In",
                                on_click="jaya:run_task",
                                variant="primary",
                            ),
                            create_label(
                                "Forgot password?",
                                style={"color": "#0066CC", "cursor": "pointer", "margin_top": "16px"}
                            ) if show_forgot_password else None,
                        ]),
                    ),
                ],
            ),
        )

    def _build_dashboard(
        self,
        title: str = "Dashboard",
        width: str = "1200px",
        height: str = "800px",
        metrics: List[Dict] = None,
        charts: List[Dict] = None,
        quick_actions: List[Dict] = None,
        sidebar: bool = True,
        **kwargs
    ) -> SceneGraph:
        """Build a dashboard SceneGraph."""
        metrics = metrics or [
            {"label": "Total Tasks", "value": "1,234", "trend": "+12%"},
            {"label": "Completed", "value": "987", "trend": "+8%"},
            {"label": "In Progress", "value": "156", "trend": "-3%"},
            {"label": "Overdue", "value": "12", "trend": "+2%"},
        ]

        children = [
            # Header
            create_panel(
                layout=LayoutType.FLEX_ROW,
                style={"padding": "16px", "border_bottom": "1px solid var(--jaya-color-border)", "gap": "8px"},
                children=[
                    create_label(title, style={"font_size": "24px", "font_weight": "600"}),
                    create_panel(layout=LayoutType.FLEX_ROW, style={"margin_left": "auto", "gap": "8px"}, children=[
                        create_button(label="New Task", on_click="jaya:run_task"),
                        create_button(label="Settings", variant="secondary", on_click="jaya:open_dialog"),
                    ]),
                ],
            ),
        ]

        if sidebar:
            # Sidebar + Main content
            children.append(
                create_panel(
                    layout=LayoutType.FLEX_ROW,
                    style={"flex": "1", "padding": "24px", "gap": "24px"},
                    children=[
                        # Sidebar
                        create_panel(
                            layout=LayoutType.FLEX_COL,
                            style={"width": "280px", "background_color": "var(--jaya-color-surface)", "border_radius": "8px", "padding": "16px"},
                            children=[
                                create_label("Navigation", style={"font_weight": "600", "margin_bottom": "16px"}),
                                create_button(label="Overview", variant="secondary"),
                                create_button(label="Tasks", variant="secondary"),
                                create_button(label="Analytics", variant="secondary"),
                                create_button(label="Integrations", variant="secondary"),
                            ],
                        ),
                        # Main area
                        create_panel(
                            layout=LayoutType.FLEX_COL,
                            style={"flex": "1", "gap": "24px"},
                            children=[
                                # Metrics row
                                create_panel(
                                    layout=LayoutType.FLEX_ROW,
                                    style={"gap": "16px"},
                                    children=[
                                        create_panel(
                                            style={"flex": "1", "background_color": "var(--jaya-color-surface)", "border_radius": "8px", "padding": "24px"},
                                            children=[
                                                create_label(m["label"], style={"font_size": "14px", "color": "var(--jaya-color-text-muted)"}),
                                                create_label(m["value"], style={"font_size": "32px", "font_weight": "600"}),
                                                create_label(m["trend"], style={"color": "var(--jaya-color-success)" if m["trend"].startswith("+") else "var(--jaya-color-danger)"}),
                                            ],
                                        ) for m in metrics
                                    ],
                                ),
                                # Chart placeholder
                                create_panel(
                                    style={"flex": "1", "background_color": "var(--jaya-color-surface)", "border_radius": "8px", "padding": "24px"},
                                    children=[
                                        create_label("Activity Chart", style={"font_weight": "600", "margin_bottom": "16px"}),
                                        create_label("[Chart would render here]", style={"color": "var(--jaya-color-text-muted)", "text_align": "center"}),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            )
        else:
            # Full width content
            children.append(
                create_panel(
                    layout=LayoutType.FLEX_COL,
                    style={"flex": "1", "padding": "24px", "gap": "24px"},
                    children=[
                        create_panel(
                            layout=LayoutType.FLEX_ROW,
                            style={"gap": "16px"},
                            children=[
                                create_panel(
                                    style={"flex": "1", "background_color": "var(--jaya-color-surface)", "border_radius": "8px", "padding": "24px"},
                                    children=[
                                        create_label(m["label"], style={"font_size": "14px", "color": "var(--jaya-color-text-muted)"}),
                                        create_label(m["value"], style={"font_size": "32px", "font_weight": "600"}),
                                        create_label(m["trend"], style={"color": "var(--jaya-color-success)" if m["trend"].startswith("+") else "var(--jaya-color-danger)"}),
                                    ],
                                ) for m in metrics
                            ],
                        ),
                    ],
                ),
            )

        return SceneGraph(
            name="Dashboard",
            description="Main dashboard with metrics and quick actions",
            root=create_window(
                title=title,
                width="1200px",
                height="800px",
                children=children,
            ),
        )

    def _build_settings_dialog(
        self,
        title: str = "Settings",
        width: str = "600px",
        height: str = "700px",
        sections: List[Dict] = None,
        **kwargs
    ) -> SceneGraph:
        """Build a settings dialog SceneGraph."""
        sections = sections or [
            {
                "title": "General",
                "fields": [
                    {"type": "text", "label": "Display Name", "placeholder": "Your name"},
                    {"type": "select", "label": "Language", "options": [{"value": "en", "label": "English"}, {"value": "id", "label": "Indonesian"}]},
                    {"type": "select", "label": "Theme", "options": [{"value": "light", "label": "Light"}, {"value": "dark", "label": "Dark"}, {"value": "system", "label": "System"}]},
                ],
            },
            {
                "title": "Privacy & Security",
                "fields": [
                    {"type": "checkbox", "label": "Allow anonymous usage analytics"},
                    {"type": "checkbox", "label": "Crash reporting"},
                    {"type": "checkbox", "label": "Auto-update"},
                ],
            },
            {
                "title": "Notifications",
                "fields": [
                    {"type": "checkbox", "label": "Email notifications"},
                    {"type": "checkbox", "label": "Push notifications"},
                    {"type": "select", "label": "Frequency", "options": [{"value": "immediate", "label": "Immediate"}, {"value": "hourly", "label": "Hourly digest"}, {"value": "daily", "label": "Daily digest"}]},
                ],
            },
        ]

        section_panels: List[Any] = []
        for section in sections:
            field_widgets: List[Any] = []
            for field in section["fields"]:
                field_type = field.get("type")
                if field_type in ("text", "email", "textarea"):
                    field_widgets.append(create_text_input(placeholder=field.get("placeholder", ""), value=""))
                elif field_type == "checkbox":
                    field_widgets.append(create_label("Checkbox: " + field["label"]))
                elif field_type == "select":
                    field_widgets.append(create_label("Select: " + field["label"]))
                elif field_type == "button":
                    field_widgets.append(create_button(label=field["label"]))
                else:
                    field_widgets.append(create_label(field.get("label", "Field")))

            section_panels.append(
                create_panel(
                    style={"background_color": "var(--jaya-color-surface)", "border_radius": "8px", "padding": "24px"},
                    children=self._compact_children([
                        create_label(section["title"], style={"font_weight": "600", "margin_bottom": "16px"}),
                        *field_widgets,
                    ]),
                )
            )

        return SceneGraph(
            name="Settings",
            description="Application settings and preferences",
            root=create_window(
                title=title,
                width=width,
                height=height,
                children=[
                    create_panel(
                        layout=LayoutType.FLEX_COL,
                        style={"padding": "24px", "gap": "24px"},
                        children=self._compact_children([
                            create_label(title, style={"font_size": "24px", "font_weight": "600"}),
                            *section_panels,
                            create_panel(
                                layout=LayoutType.FLEX_ROW,
                                style={"justify_content": "flex-end", "gap": "12px"},
                                children=[
                                    create_button(label="Cancel", variant="secondary", on_click="jaya:close_dialog"),
                                    create_button(label="Save Changes", variant="primary", on_click="jaya:run_task"),
                                ],
                            ),
                        ]),
                    ),
                ],
            ),
        )

    def _build_file_explorer(
        self,
        title: str = "File Explorer",
        width: str = "400px",
        height: str = "600px",
        root_path: str = "/",
        show_hidden: bool = False,
        multi_select: bool = False,
        file_filters: List[str] = None,
        **kwargs
    ) -> SceneGraph:
        """Build a file explorer SceneGraph."""
        return SceneGraph(
            name="File Explorer",
            description="File system browser",
            root=create_window(
                title=title,
                width=width,
                height=height,
                children=[
                    create_panel(
                        layout=LayoutType.FLEX_COL,
                        children=[
                            # Toolbar
                            create_panel(
                                layout=LayoutType.FLEX_ROW,
                                style={"padding": "8px", "border_bottom": "1px solid var(--jaya-color-border)", "gap": "8px"},
                                children=[
                                    create_button(label="↑", variant="secondary", on_click="jaya:run_task"),
                                    create_button(label="🔄", variant="secondary", on_click="jaya:run_task"),
                                    create_button(label="🏠", variant="secondary", on_click="jaya:run_task"),
                                    create_panel(style={"flex": "1"}),
                                    create_button(label="New Folder", variant="secondary", on_click="jaya:run_task"),
                                ],
                            ),
                            # Path bar
                            create_panel(
                                style={"padding": "8px 12px", "background_color": "var(--jaya-color-surface)", "border_bottom": "1px solid var(--jaya-color-border)"},
                                children=[
                                    create_label("📁 Home > Documents > Projects", style={"font_family": "monospace", "font_size": "13px"}),
                                ],
                            ),
                            # File tree
                            create_panel(
                                style={"flex": "1", "overflow_y": "auto", "padding": "8px"},
                                children=[
                                    create_label("📁 Documents", style={"font_weight": "500"}),
                                    create_label("📁 Downloads"),
                                    create_label("📁 Pictures"),
                                    create_label("📄 README.md"),
                                    create_label("📄 config.yaml"),
                                    create_label("📁 Projects"),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

    def _build_chat_interface(
        self,
        title: str = "JAYA Chat",
        width: str = "500px",
        height: str = "700px",
        placeholder: str = "Type a message...",
        send_button_text: str = "Send",
        show_timestamps: bool = True,
        **kwargs
    ) -> SceneGraph:
        """Build a chat interface SceneGraph."""
        return SceneGraph(
            name="Chat",
            description="Chat interface for JAYA conversation",
            root=create_window(
                title=title,
                width=width,
                height=height,
                children=[
                    create_panel(
                        layout=LayoutType.FLEX_COL,
                        children=[
                            # Messages area
                            create_panel(
                                style={"flex": "1", "overflow_y": "auto", "padding": "16px", "gap": "12px"},
                                children=[
                                    create_panel(
                                        style={"background_color": "var(--jaya-color-surface)", "border_radius": "12px", "padding": "12px 16px", "max_width": "80%", "align_self": "flex-start"},
                                        children=[
                                            create_label("Hello! How can I help you today?", style={"color": "var(--jaya-color-text)"}),
                                        ],
                                    ),
                                ],
                            ),
                            # Input area
                            create_panel(
                                layout=LayoutType.FLEX_ROW,
                                style={"padding": "16px", "border_top": "1px solid var(--jaya-color-border)", "gap": "8px"},
                                children=[
                                    create_text_input(
                                        placeholder=placeholder,
                                        style={"flex": "1"},
                                        on_change="jaya:update_state",
                                    ),
                                    create_button(label=send_button_text, variant="primary", on_click="jaya:run_task"),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

    def _build_confirm_dialog(
        self,
        title: str = "Confirm",
        message: str = "Are you sure?",
        confirm_text: str = "Yes",
        cancel_text: str = "No",
        variant: str = "warning",  # warning, danger, info
        **kwargs
    ) -> SceneGraph:
        """Build a confirmation dialog SceneGraph."""
        variant_colors = {
            "warning": "#FFC107",
            "danger": "#DC3545",
            "info": "#0066CC",
        }
        variant_colors.get(variant, "#FFC107")

        return SceneGraph(
            name="Confirm Dialog",
            description="Confirmation dialog",
            root=create_window(
                title=title,
                width="400px",
                height="200px",
                children=[
                    create_panel(
                        layout=LayoutType.FLEX_COL,
                        style={"padding": "24px", "gap": "16px"},
                        children=[
                            create_label(message, style={"font_size": "16px", "text_align": "center"}),
                            create_panel(
                                layout=LayoutType.FLEX_ROW,
                                style={"justify_content": "flex-end", "gap": "12px", "margin_top": "8px"},
                                children=[
                                    create_button(label=cancel_text, variant="secondary", on_click="jaya:close_dialog"),
                                    create_button(label=confirm_text, variant="primary", on_click="jaya:run_task"),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

    def _build_progress_dialog(
        self,
        title: str = "Working...",
        message: str = "Please wait...",
        show_percentage: bool = False,
        cancellable: bool = False,
        indeterminate: bool = True,
        **kwargs
    ) -> SceneGraph:
        """Build a progress dialog SceneGraph."""
        progress_children = self._compact_children([
            create_label(message, style={"text_align": "center"}),
            create_label("[Progress bar would render here]", style={"color": "var(--jaya-color-text-muted)", "width": "100%"}),
            create_button(label="Cancel", variant="secondary", on_click="jaya:close_dialog") if cancellable else None,
        ])

        return SceneGraph(
            name="Progress Dialog",
            description="Progress indicator dialog",
            root=create_window(
                title=title,
                width="400px",
                height="150px",
                children=[
                    create_panel(
                        layout=LayoutType.FLEX_COL,
                        style={"padding": "24px", "gap": "16px", "align_items": "center"},
                        children=progress_children,
                    ),
                ],
            ),
        )

    def _build_list_view(
        self,
        title: str = "List View",
        width: str = "800px",
        height: str = "600px",
        columns: List[Dict] = None,
        data: List[Dict] = None,
        sortable: bool = True,
        selectable: bool = False,
        actions: List[Dict] = None,
        **kwargs
    ) -> SceneGraph:
        """Build a list/table view SceneGraph."""
        columns = columns or [
            {"key": "name", "label": "Name", "width": "30%"},
            {"key": "status", "label": "Status", "width": "15%"},
            {"key": "date", "label": "Date", "width": "20%"},
            {"key": "actions", "label": "Actions", "width": "35%"},
        ]
        data = data or [
            {"name": "Project Alpha", "status": "Active", "date": "2024-01-15", "actions": ["Edit", "Delete"]},
            {"name": "Project Beta", "status": "Pending", "date": "2024-01-10", "actions": ["Edit", "Delete"]},
            {"name": "Project Gamma", "status": "Completed", "date": "2024-01-05", "actions": ["View", "Archive"]},
        ]

        return SceneGraph(
            name="List View",
            description="Data table with sorting and actions",
            root=create_window(
                title=title,
                width=width,
                height=height,
                children=[
                    create_panel(
                        layout=LayoutType.FLEX_COL,
                        children=[
                            # Toolbar
                            create_panel(
                                layout=LayoutType.FLEX_ROW,
                                style={"padding": "16px", "border_bottom": "1px solid var(--jaya-color-border)", "gap": "8px"},
                                children=[
                                    create_label(title, style={"font_size": "18px", "font_weight": "600"}),
                                    create_panel(style={"flex": "1"}),
                                    create_button(label="Add New", variant="primary", on_click="jaya:run_task"),
                                ],
                            ),
                            # Table
                            create_panel(
                                style={"flex": "1", "overflow": "auto", "padding": "16px"},
                                children=[
                                    create_label("[Table would render here with columns: " + ", ".join(c["label"] for c in columns) + "]", style={"color": "var(--jaya-color-text-muted)"}),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

    def _build_form(
        self,
        title: str = "Form",
        width: str = "500px",
        height: str = "auto",
        fields: List[Dict] = None,
        submit_text: str = "Submit",
        cancel_text: str = "Cancel",
        validation: Dict = None,
        **kwargs
    ) -> SceneGraph:
        """Build a form SceneGraph."""
        fields = fields or [
            {"type": "text", "label": "Full Name", "placeholder": "Enter your name", "required": True},
            {"type": "email", "label": "Email", "placeholder": "Enter your email", "required": True},
            {"type": "textarea", "label": "Message", "placeholder": "Enter your message", "required": False},
        ]

        return SceneGraph(
            name="Form",
            description="Data entry form",
            root=create_window(
                title=title,
                width=width,
                height=height,
                children=[
                    create_panel(
                        layout=LayoutType.FLEX_COL,
                        style={"padding": "24px", "gap": "16px"},
                        children=[
                            create_label(title, style={"font_size": "24px", "font_weight": "600"}),
                            *[create_text_input(
                                placeholder=field["placeholder"],
                                on_change="jaya:update_state",
                            ) if field["type"] in ("text", "email") else
                            create_text_input(
                                placeholder=field["placeholder"],
                                on_change="jaya:update_state",
                            ) if field["type"] == "textarea" else
                            create_label(field["label"])
                            for field in fields
                            ],
                            create_panel(
                                layout=LayoutType.FLEX_ROW,
                                style={"justify_content": "flex-end", "gap": "12px", "margin_top": "8px"},
                                children=[
                                    create_button(label=cancel_text, variant="secondary", on_click="jaya:close_dialog"),
                                    create_button(label=submit_text, variant="primary", on_click="jaya:run_task"),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

    def _build_generic_dialog(
        self,
        title: str = "Dialog",
        width: str = "500px",
        height: str = "400px",
        content: str = "",
        buttons: List[Dict] = None,
        **kwargs
    ) -> SceneGraph:
        """Build a generic dialog SceneGraph."""
        buttons = buttons or [
            {"label": "Cancel", "variant": "secondary", "action": "jaya:close_dialog"},
            {"label": "OK", "variant": "primary", "action": "jaya:run_task"},
        ]

        return SceneGraph(
            name="Generic Dialog",
            description="Generic dialog with custom content",
            root=create_window(
                title=title,
                width=width,
                height=height,
                children=[
                    create_panel(
                        layout=LayoutType.FLEX_COL,
                        style={"padding": "24px", "gap": "16px"},
                        children=[
                            create_label(content or "Dialog content goes here", style={"font_size": "16px"}),
                            create_panel(
                                layout=LayoutType.FLEX_ROW,
                                style={"justify_content": "flex-end", "gap": "12px", "margin_top": "8px"},
                                children=[
                                    create_button(
                                        label=btn["label"],
                                        variant=btn.get("variant", "secondary"),
                                        on_click=btn.get("action", "jaya:close_dialog"),
                                    ) for btn in buttons
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

    # ============================================================
    # Public API
    # ============================================================

    def match_intent(self, user_input: str) -> List[IntentMatch]:
        """Match user input to known intent patterns."""
        matches = []

        # Use intent engine for prediction
        predictions = self.intent_engine.predict_intent(user_input, top_k=5)

        for predicted_command, confidence in predictions:
            # Match against template patterns
            for template_name, template in self.templates.items():
                for pattern in template.intent_patterns:
                    if pattern.lower() in predicted_command.lower() or pattern.lower() in user_input.lower():
                        matches.append(IntentMatch(
                            intent_type=template_name,
                            confidence=confidence,
                            parameters={},
                            suggested_ui=template_name,
                        ))

        # Also check direct pattern matching
        user_lower = user_input.lower()
        for template_name, template in self.templates.items():
            for pattern in template.intent_patterns:
                if pattern.lower() in user_lower:
                    matches.append(IntentMatch(
                        intent_type=template_name,
                        confidence=0.8,
                        parameters={},
                        suggested_ui=template_name,
                    ))

        # Sort by confidence and deduplicate
        seen = set()
        unique_matches = []
        for match in sorted(matches, key=lambda m: -m.confidence):
            if match.intent_type not in seen:
                seen.add(match.intent_type)
                unique_matches.append(match)

        return unique_matches[:5]

    def extract_parameters(self, user_input: str, template_name: str) -> Dict[str, Any]:
        """Extract parameters from user input for a specific template."""
        template = self.templates.get(template_name)
        if not template:
            return {}

        params = {}
        # Simple parameter extraction - in production, use NLP
        # For now, return defaults
        for param in template.required_params:
            if param == "title":
                params[param] = "Untitled"
            elif param == "message":
                params[param] = "Are you sure?"
            elif param == "columns":
                params[param] = [{"key": "name", "label": "Name"}, {"key": "value", "label": "Value"}]
            elif param == "fields":
                params[param] = [{"type": "text", "label": "Name", "placeholder": "Enter name"}]
            elif param == "root_path":
                params[param] = "/"

        for param in template.optional_params:
            params[param] = None

        return params

    async def process_intent(self, user_input: str) -> Dict[str, Any]:
        """Process user input through the full pipeline: Intent → UI → Feature."""
        # 1. Match intent
        matches = self.match_intent(user_input)

        if not matches:
            return {
                "success": False,
                "error": "No matching intent found",
                "suggestions": ["Try: 'show login dialog', 'create dashboard', 'open settings'"],
            }

        best_match = matches[0]
        template_name = best_match.suggested_ui

        # 2. Extract parameters
        params = self.extract_parameters(user_input, template_name)

        # 3. Build SceneGraph
        template = self.templates.get(template_name)
        if not template:
            return {"success": False, "error": f"Template not found: {template_name}"}

        try:
            scene = template.builder(**params)
        except Exception as e:
            return {"success": False, "error": f"Failed to build UI: {e}"}

        # 4. Compile to feature
        compile_result = await self.bridge.compile_intent_to_feature(
            intent=user_input,
            feature_name=template.name,
            context={"scene": scene.to_dict()},
        )

        if not compile_result.get("success"):
            return {"success": False, "error": f"Compilation failed: {compile_result.get('error')}"}

        # 5. Mount feature
        feature_id = compile_result["data"]["feature_id"]
        mount_result = await self.bridge.mount_feature(feature_id, "dialog-root")

        if not mount_result.get("success"):
            return {"success": False, "error": f"Mount failed: {mount_result.get('error')}"}

        return {
            "success": True,
            "intent": template_name,
            "confidence": best_match.confidence,
            "feature_id": feature_id,
            "mount_point": "dialog-root",
            "scene": scene.to_dict(),
        }

    def list_templates(self) -> List[Dict[str, Any]]:
        """List all available UI templates."""
        return [
            {
                "name": name,
                "description": template.description,
                "patterns": template.intent_patterns,
                "required_params": template.required_params,
                "optional_params": template.optional_params,
            }
            for name, template in self.templates.items()
        ]


# Convenience function for quick usage
async def create_ui_from_intent(
    bridge: JayaBridge,
    user_input: str,
    intent_engine: Optional[IntentEngine] = None,
) -> Dict[str, Any]:
    """Quick function to create UI from natural language intent."""
    pipeline = IntentToUIPipeline(bridge, intent_engine)
    return await pipeline.process_intent(user_input)


# Example usage
if __name__ == "__main__":
    async def demo():
        # This would be used with actual bridge
        print("IntentToUIPipeline ready")
        print("Available templates:")
        pipeline = IntentToUIPipeline(None)
        for t in pipeline.list_templates():
            print(f"  - {t['name']}: {t['description']}")
            print(f"    Patterns: {t['patterns']}")

    asyncio.run(demo())
