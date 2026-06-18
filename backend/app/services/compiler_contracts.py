from typing import Protocol

from backend.app.domain.compiler import (
    CompilationBundle,
    CompilationPassPlan,
    CompilationPassResult,
    CoverageReport,
    SourceManifest,
)
from backend.app.domain.models import SourceRef


class CompilerLLMClient(Protocol):
    async def profile_source(self, source: SourceRef) -> SourceManifest:
        """Read a source and produce a semantic manifest and dynamic pass plan."""

    async def compile_source_pass(
        self,
        source: SourceRef,
        manifest: SourceManifest,
        plan: CompilationPassPlan,
        existing: CompilationBundle,
    ) -> CompilationPassResult:
        """Compile one model-planned knowledge pass with source-local provenance."""

    async def audit_compilation(
        self,
        source: SourceRef,
        manifest: SourceManifest,
        compilation: CompilationBundle,
        iteration: int,
    ) -> CoverageReport:
        """Compare compiled knowledge with the source and identify material gaps."""
