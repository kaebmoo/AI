"""Schema metadata, view builder, and dimension family admin endpoints."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api import deps
from app.models.schema_models import SchemaMetadata
from app.models.user import User
from app.schemas.admin_schemas import (
    DimensionFamilyAnalyzeRequest,
    DimensionFamilyAnalyzeResponse,
    DimensionFamilyBatchUpdate,
    DimensionFamilyBatchUpdateResponse,
    DimensionFamilyColumn,
    DimensionFamilyItem,
    DimensionFamilyListResponse,
    DimensionFamilySuggestion,
    PropagateMetadataResponse,
    SchemaMetadataCreate,
    SchemaMetadataListResponse,
    SchemaMetadataResponse,
    SchemaMetadataUpdate,
    ViewColumnMappingResponse,
    ViewCreateRequest,
    ViewMappingSuggestion,
    ViewMappingsListResponse,
    ViewSummaryItem,
    ViewSummaryListResponse,
)
from app.services.ai_service import AIService
from app.services.provenance import ACTIVE, MANUAL, mark_human_edit
from app.services.query_engine import clear_query_cache
from app.services.schema_service import SchemaService

from ._shared import ensure_metadata_rows, mark_brain_dirty
from app.core.time_utils import utcnow

router = APIRouter()


@router.get("/schema/columns", response_model=SchemaMetadataListResponse)
def list_schema_columns(
    table_name: Optional[str] = Query(None, description="Filter by table name"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """List all column metadata. Admin only."""
    query = db.query(SchemaMetadata)
    if table_name:
        query = query.filter(SchemaMetadata.table_name == table_name)

    columns = query.order_by(SchemaMetadata.table_name, SchemaMetadata.column_name).all()
    return SchemaMetadataListResponse(
        columns=[SchemaMetadataResponse.model_validate(column) for column in columns],
        total=len(columns),
    )


@router.get("/schema/columns/{column_id}", response_model=SchemaMetadataResponse)
def get_schema_column(
    column_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Get single column metadata. Admin only."""
    column = db.query(SchemaMetadata).filter(SchemaMetadata.id == column_id).first()
    if not column:
        raise HTTPException(status_code=404, detail="Column metadata not found")
    return SchemaMetadataResponse.model_validate(column)


@router.post("/schema/columns", response_model=SchemaMetadataResponse, status_code=status.HTTP_201_CREATED)
def create_schema_column(
    data: SchemaMetadataCreate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service),
):
    """Add new column metadata. Admin only."""
    existing = db.query(SchemaMetadata).filter(
        SchemaMetadata.table_name == data.table_name,
        SchemaMetadata.column_name == data.column_name,
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Column {data.column_name} in table {data.table_name} already exists",
        )

    column = SchemaMetadata(**data.model_dump(), source=MANUAL, status=ACTIVE)
    db.add(column)
    db.commit()
    db.refresh(column)

    schema_service.refresh_cache()
    clear_query_cache()
    mark_brain_dirty()
    return SchemaMetadataResponse.model_validate(column)


@router.put("/schema/columns/{column_id}", response_model=SchemaMetadataResponse)
def update_schema_column(
    column_id: int,
    data: SchemaMetadataUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service),
):
    """Update column metadata. Admin only."""
    column = db.query(SchemaMetadata).filter(SchemaMetadata.id == column_id).first()
    if not column:
        raise HTTPException(status_code=404, detail="Column metadata not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(column, key, value)
    mark_human_edit(column, "schema_metadata", update_data)

    column.updated_at = utcnow()
    db.commit()
    db.refresh(column)

    schema_service.refresh_cache()
    clear_query_cache()
    mark_brain_dirty()
    return SchemaMetadataResponse.model_validate(column)


@router.delete("/schema/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schema_column(
    column_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service),
):
    """Delete column metadata. Admin only."""
    column = db.query(SchemaMetadata).filter(SchemaMetadata.id == column_id).first()
    if not column:
        raise HTTPException(status_code=404, detail="Column metadata not found")

    db.delete(column)
    db.commit()

    schema_service.refresh_cache()
    clear_query_cache()
    mark_brain_dirty()
    return None


def service_for_table(table_name: str, service: SchemaService) -> SchemaService:
    """The SchemaService that inspects this table where it really lives (Phase 4d): a file-source
    view is read through its source; anything else through the legacy business DB, as before."""
    from app.services import data_sources

    owner = data_sources.registered_tables(service.get_config_engine()).get(table_name)
    if not owner:
        return service
    return SchemaService(db_engine=service.get_config_engine(),
                         business_engine=data_sources.source_resolver.for_context(owner["context"]).engine)


@router.get("/schema/tables", response_model=List[str])
def list_tables(
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
):
    """List all tables available for view creation — legacy business DB + file-source views."""
    from app.services.data_sources import registered_tables

    return sorted(set(service.get_all_tables()) | set(registered_tables(service.get_config_engine())))


@router.post("/schema/views", status_code=status.HTTP_201_CREATED)
def create_view(
    data: ViewCreateRequest,
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
):
    """Create a new view from a source table."""
    try:
        mapping_dicts = [mapping.model_dump() for mapping in data.mapping]
        service.create_custom_view(
            view_name=data.view_name,
            source_table=data.source_table,
            mapping=mapping_dicts,
        )
        clear_query_cache()
        mark_brain_dirty()
        return {
            "status": "success",
            "message": f"View {data.view_name} created with column mappings and metadata propagated",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create view: {str(exc)}") from exc


@router.get("/schema/tables/{table_name}/suggest-mapping", response_model=List[ViewMappingSuggestion])
async def suggest_view_mapping(
    table_name: str,
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
    ai_service: AIService = Depends(deps.get_ai_service),
):
    """Get AI-powered mapping suggestions for a table."""
    try:
        columns = service_for_table(table_name, service).get_table_info(table_name)
        samples = service_for_table(table_name, service).get_sample_values(table_name)
        suggestions_data = await ai_service.suggest_mappings(columns, samples)

        suggestions = []
        for suggestion in suggestions_data:
            suggestions.append(
                ViewMappingSuggestion(
                    col=suggestion.get("col"),
                    suggested_alias=suggestion.get("alias"),
                    reason=suggestion.get("reason"),
                )
            )
        return suggestions
    except Exception as exc:
        columns = service_for_table(table_name, service).get_table_info(table_name)
        return [
            ViewMappingSuggestion(
                col=column["name"],
                suggested_alias=column["name"].lower(),
                reason=f"Fallback error: {str(exc)}",
            )
            for column in columns
        ]


@router.get("/schema/views/summary", response_model=ViewSummaryListResponse)
def list_views_summary(
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
):
    """List all views with column mapping summary."""
    views = service.list_views_with_mappings()
    return ViewSummaryListResponse(
        views=[ViewSummaryItem(**view) for view in views],
        total=len(views),
    )


@router.get("/schema/views/{view_name}/mappings", response_model=ViewMappingsListResponse)
def get_view_mappings(
    view_name: str,
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
):
    """Get column mappings for a view."""
    mappings = service.get_view_column_mappings(view_name)
    return ViewMappingsListResponse(
        view_name=view_name,
        mappings=[ViewColumnMappingResponse(**mapping) for mapping in mappings],
        total=len(mappings),
    )


@router.post("/schema/views/{view_name}/propagate-metadata", response_model=PropagateMetadataResponse)
def propagate_view_metadata(
    view_name: str,
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
):
    """Propagate metadata from source table(s) to a view."""
    result = service.propagate_metadata_to_view(view_name)
    mark_brain_dirty()
    missing = result.get("missing_columns", [])
    message = f"Propagated: {result['created']} created, {result['updated']} updated, {result.get('skipped', 0)} skipped"
    if missing:
        message += f". {len(missing)} columns have no source metadata: {', '.join(item['view_column'] for item in missing)}"
    return PropagateMetadataResponse(
        view_name=view_name,
        created=result["created"],
        updated=result["updated"],
        skipped=result.get("skipped", 0),
        missing_columns=missing,
        message=message,
    )


@router.get("/schema/dimension-families", response_model=DimensionFamilyListResponse)
def get_dimension_families(
    table_name: str = Query(..., description="Table name to get families for"),
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
):
    """Get merged dimension families with source tracking."""
    families_data = service.get_dimension_families_with_source(table_name)
    families = [
        DimensionFamilyItem(
            family_name=family["family_name"],
            columns=[DimensionFamilyColumn(**column) for column in family["columns"]],
            source=family["source"],
        )
        for family in families_data
    ]
    return DimensionFamilyListResponse(table_name=table_name, families=families, total=len(families))


@router.post("/schema/dimension-families/analyze", response_model=DimensionFamilyAnalyzeResponse)
async def analyze_dimension_families(
    request: DimensionFamilyAnalyzeRequest,
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
    ai_service: AIService = Depends(deps.get_ai_service),
):
    """LLM analyzes columns and sample values to suggest dimension families."""
    import json as _json
    import re as _re

    columns = service_for_table(request.table_name, service).get_table_info(request.table_name)
    samples = service.get_sample_values(request.table_name)

    column_info = []
    for column in columns:
        name = column["name"]
        sample_vals = samples.get(name, [])[:3]
        column_info.append(f"- {name} ({column['type']}): {sample_vals}")

    column_text = "\n".join(column_info)
    prompt = f'''วิเคราะห์คอลัมน์ในตาราง "{request.table_name}" แล้วจัดกลุ่ม Dimension Family
(คอลัมน์ที่เกี่ยวข้องกันควรอยู่กลุ่มเดียวกัน เช่น SECTION + SECTION_ABBR, GL_CODE + GL_NAME + GL_GROUP)

คอลัมน์ทั้งหมด:
{column_text}

ตอบในรูปแบบ JSON:
```json
{{
  "families": [
    {{"family_name": "org_section", "columns": ["SECTION", "SECTION_ABBR"]}},
    ...
  ],
  "reasoning": "อธิบายเหตุผลสั้นๆ"
}}
```'''

    try:
        result = await ai_service.provider.generate_content(
            prompt,
            system_prompt="คุณเป็น data analyst ที่เชี่ยวชาญการจัดกลุ่มคอลัมน์",
        )
        json_match = _re.search(r"```json\s*(\{.*?\})\s*```", result, _re.DOTALL)
        parsed = _json.loads(json_match.group(1) if json_match else result)
        suggested = [
            DimensionFamilySuggestion(family_name=family["family_name"], columns=family["columns"])
            for family in parsed.get("families", [])
        ]
        reasoning = parsed.get("reasoning", "")
    except Exception as exc:
        suggested = []
        reasoning = f"LLM analysis failed: {str(exc)}"

    return DimensionFamilyAnalyzeResponse(
        table_name=request.table_name,
        suggested_families=suggested,
        llm_reasoning=reasoning,
        provider_used=getattr(ai_service.provider, "name", "unknown"),
    )


@router.put("/schema/dimension-families", response_model=DimensionFamilyBatchUpdateResponse)
def batch_update_dimension_families(
    request: DimensionFamilyBatchUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    service: SchemaService = Depends(deps.get_schema_service),
):
    """Batch save dimension_group assignments to DB."""
    col_names = [assignment.column_name for assignment in request.assignments]
    ensure_metadata_rows(db, request.table_name, col_names, service)

    updated = 0
    for assignment in request.assignments:
        row = db.query(SchemaMetadata).filter(
            SchemaMetadata.table_name == request.table_name,
            SchemaMetadata.column_name == assignment.column_name,
        ).first()
        if row:
            row.dimension_group = assignment.dimension_group
            mark_human_edit(row, "schema_metadata", ["dimension_group"])
            updated += 1

    db.commit()
    mark_brain_dirty()

    families_data = service.get_dimension_families_with_source(request.table_name)
    families = [
        DimensionFamilyItem(
            family_name=family["family_name"],
            columns=[DimensionFamilyColumn(**column) for column in family["columns"]],
            source=family["source"],
        )
        for family in families_data
    ]
    return DimensionFamilyBatchUpdateResponse(updated_count=updated, families=families)


@router.post("/schema/dimension-families/auto-populate", response_model=DimensionFamilyBatchUpdateResponse)
def auto_populate_dimension_families(
    table_name: str = Query(..., description="Table/view name"),
    overwrite: bool = Query(False, description="Overwrite existing DB assignments"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    service: SchemaService = Depends(deps.get_schema_service),
):
    """Run auto-detect and save results to DB."""
    from app.services.dimension_detector import detect_families

    columns = service_for_table(table_name, service).get_table_info(table_name)
    all_col_names = [column["name"] for column in columns]
    auto_families = detect_families(all_col_names)

    all_family_cols = [column for cols in auto_families.values() for column in cols]
    ensure_metadata_rows(db, table_name, all_family_cols, service)

    updated = 0
    for family_name, cols in auto_families.items():
        for col_name in cols:
            row = db.query(SchemaMetadata).filter(
                SchemaMetadata.table_name == table_name,
                SchemaMetadata.column_name == col_name,
            ).first()
            if row and (overwrite or not row.dimension_group):
                row.dimension_group = family_name
                updated += 1

    db.commit()
    mark_brain_dirty()

    families_data = service.get_dimension_families_with_source(table_name)
    families = [
        DimensionFamilyItem(
            family_name=family["family_name"],
            columns=[DimensionFamilyColumn(**column) for column in family["columns"]],
            source=family["source"],
        )
        for family in families_data
    ]
    return DimensionFamilyBatchUpdateResponse(updated_count=updated, families=families)
