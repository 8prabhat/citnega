"""wizard_base — re-exports WizardBase from workspace to avoid circular imports."""

from citnega.apps.tui.slash_commands.workspace import WizardBase

__all__ = ["WizardBase"]
