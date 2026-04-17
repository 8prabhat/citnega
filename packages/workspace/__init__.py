"""
citnega.packages.workspace — self-creating workspace support.

Users create agents, tools, and workflows from inside the TUI via
/createtool, /createagent, /createworkflow.  Artifacts are generated
as Python files, validated, written to the workfolder, and registered
live without restarting citnega.

Public surface:
  ScaffoldSpec       — data class describing what to generate
  FallbackTemplates  — static code generation (no LLM required)
  CodeValidator      — AST-based pre-write validation
  ContractVerifier   — runtime contract validation for onboarding
  OnboardingReport   — workspace bundle manifest verification outcomes
  ScaffoldGenerator  — LLM-first, fallback-second code generator
  WorkspaceWriter    — writes files to workfolder subdirs
  DynamicLoader      — hot-loads Python files into callables
"""

from citnega.packages.workspace.contract_verifier import ContractVerificationError, ContractVerifier
from citnega.packages.workspace.loader import DynamicLoader
from citnega.packages.workspace.onboarding import (
    WorkspaceOnboardingError,
    WorkspaceOnboardingReport,
    generate_workspace_bundle_manifest,
    verify_workspace_onboarding,
    write_workspace_bundle_manifest,
)
from citnega.packages.workspace.scaffold import ScaffoldGenerator
from citnega.packages.workspace.templates import FallbackTemplates, ScaffoldSpec
from citnega.packages.workspace.tester import CallableTester, CodeTestResult
from citnega.packages.workspace.validator import CodeValidator, ValidationResult
from citnega.packages.workspace.writer import WorkspaceWriter

__all__ = [
    "CallableTester",
    "CodeTestResult",
    "CodeValidator",
    "ContractVerificationError",
    "ContractVerifier",
    "DynamicLoader",
    "FallbackTemplates",
    "ScaffoldGenerator",
    "ScaffoldSpec",
    "ValidationResult",
    "WorkspaceOnboardingError",
    "WorkspaceOnboardingReport",
    "WorkspaceWriter",
    "generate_workspace_bundle_manifest",
    "verify_workspace_onboarding",
    "write_workspace_bundle_manifest",
]
