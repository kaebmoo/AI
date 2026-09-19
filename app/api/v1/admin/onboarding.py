"""Context onboarding admin endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.schemas.admin_schemas import (
    AnalysisSummary,
    ApplySqlRequest,
    AvailableView,
    AvailableViewsResponse,
    ConfigSummary,
    InspectRequest,
    InspectionSummary,
    OnboardingRequest,
    OnboardingResponse,
    ValidationSummary,
    ValidateRequest,
)
from app.services.schema_service import SchemaService

from . import _get_business_db_path
from ._shared import mark_brain_dirty
from app.services.data_sources import registered_tables

router = APIRouter()


def _refuse_contract_driven(view_name: str) -> None:
    """Onboarding inspects the legacy business DB. A file-source table has a stale copy there under the
    same name: onboarding it would overwrite the knowledge generated from the owner's contract."""
    owner = registered_tables().get(view_name)
    if owner:
        raise HTTPException(status_code=400, detail=(
            f"{view_name} เป็นตารางของ file source (context '{owner['context']}') — ความรู้มาจาก contract; "
            f"ใช้ POST /admin/sources/register แทนการ onboard"))


@router.get("/contexts/onboard/available-views", response_model=AvailableViewsResponse)
def list_onboardable_views(
    current_user: User = Depends(deps.require_admin),
):
    """List views/tables with their onboarding status."""
    from app.services.context_onboarding import ContextOnboardingService

    service = ContextOnboardingService(_get_business_db_path())
    try:
        result = service.list_available_views()
        return AvailableViewsResponse(
            unconfigured=[AvailableView(**view) for view in result["unconfigured"]],
            configured=[AvailableView(**view) for view in result["configured"]],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/contexts/onboard", response_model=OnboardingResponse)
async def onboard_context(
    request: OnboardingRequest,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Full context onboarding pipeline."""
    from app.services.context_onboarding import ContextOnboardingService

    _refuse_contract_driven(request.view_name)
    service = ContextOnboardingService(_get_business_db_path())

    try:
        inspection = service.inspect(request.view_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Inspection failed: {str(exc)}") from exc

    inspection_summary = InspectionSummary(
        row_count=inspection.row_count,
        columns=len(inspection.columns),
        detected_structure=inspection.detected_structure,
        quality_issues=len(inspection.quality_issues),
    )
    if request.inspect_only:
        return OnboardingResponse(status="inspect_only", inspection=inspection_summary)

    try:
        analysis = await service.analyze(
            inspection,
            provider=request.provider,
            model=request.model,
            api_url=request.api_url,
        )
        config = service.generate_config(analysis, view_name=request.view_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(exc)}") from exc

    apply_result = service.apply(config, dry_run=request.dry_run)

    validation_summary = None
    if not request.dry_run:
        try:
            validation = await service.validate(request.view_name)
            validation_summary = ValidationSummary(
                passed=validation.passed,
                results=validation.test_results,
                issues=validation.issues if hasattr(validation, "issues") else [],
            )
            try:
                from app.db.session import business_engine, config_engine
                schema_service = SchemaService(db_engine=config_engine, business_engine=business_engine)
                schema_service.refresh_cache()
            except Exception:
                pass
            mark_brain_dirty()
        except Exception:
            pass

    return OnboardingResponse(
        status="applied" if not request.dry_run else "preview",
        inspection=inspection_summary,
        analysis=AnalysisSummary(
            data_structure=analysis.get("data_structure", {}),
            context=analysis.get("context", {}),
            rules_count=len(analysis.get("business_rules", [])),
            examples_count=len(analysis.get("golden_examples", [])),
            mappings_count=len(analysis.get("semantic_mappings", [])),
        ),
        config=ConfigSummary(
            summary=config.summary,
            sql_count=len(config.sql_statements),
            sql_statements=config.sql_statements if request.dry_run else None,
        ),
        apply=apply_result if not request.dry_run else None,
        validation=validation_summary,
    )


@router.post("/contexts/onboard/inspect")
async def inspect_context(
    request: InspectRequest,
    current_user: User = Depends(deps.require_admin),
):
    """Lightweight inspection only."""
    from app.services.context_onboarding import ContextOnboardingService

    _refuse_contract_driven(request.view_name)
    service = ContextOnboardingService(_get_business_db_path())
    try:
        inspection = service.inspect(request.view_name)
        return {"status": "ok", "inspection": inspection.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/contexts/onboard/apply-sql")
async def apply_sql_statements(
    request: ApplySqlRequest,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Apply pre-generated SQL statements directly."""
    if not request.sql_statements:
        raise HTTPException(status_code=400, detail="sql_statements is empty")
    _refuse_contract_driven(request.view_name)

    from app.services.context_onboarding import ContextOnboardingService

    service = ContextOnboardingService(_get_business_db_path())
    try:
        apply_result = service.apply_sql_statements(request.sql_statements)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Apply failed: {str(exc)}") from exc

    validation_summary = None
    try:
        validation = await service.validate(request.view_name)
        validation_summary = {
            "passed": validation.passed,
            "results": validation.test_results,
            "issues": validation.issues if hasattr(validation, "issues") else [],
        }
        try:
            from app.db.session import business_engine, config_engine
            schema_service = SchemaService(db_engine=config_engine, business_engine=business_engine)
            schema_service.refresh_cache()
        except Exception:
            pass
        mark_brain_dirty()
    except Exception:
        pass

    return {"status": "applied", "apply": apply_result, "validation": validation_summary}


@router.post("/contexts/onboard/validate")
async def validate_context(
    request: ValidateRequest,
    current_user: User = Depends(deps.require_admin),
):
    """Validate that config exists for a view."""
    from app.services.context_onboarding import ContextOnboardingService

    service = ContextOnboardingService(_get_business_db_path())
    try:
        validation = await service.validate(request.view_name)
        return {
            "status": "ok",
            "passed": validation.passed,
            "results": validation.test_results,
            "issues": validation.issues,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
