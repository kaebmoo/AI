"""
NT AI Assistant - Admin API
=================================
Admin API endpoints for schema metadata, semantic mappings, business rules,
and golden examples management.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime
from app.api import deps
from app.services.ai_service import AIService
from app.models.user import User
from app.models.schema_models import SchemaMetadata, SchemaSemanticMapping, SchemaBusinessRule
from app.models.feedback_models import GoldenExample
from app.schemas.admin_schemas import (
    SchemaMetadataCreate, SchemaMetadataUpdate, SchemaMetadataResponse, SchemaMetadataListResponse,
    SemanticMappingCreate, SemanticMappingUpdate, SemanticMappingResponse, SemanticMappingListResponse,
    BusinessRuleCreate, BusinessRuleUpdate, BusinessRuleResponse, BusinessRuleListResponse,
    GoldenExampleCreate, GoldenExampleUpdate, GoldenExampleResponse, GoldenExampleListResponse,
    SchemaContextCreate, SchemaContextUpdate, SchemaContextResponse, SchemaContextListResponse,
    ViewCreateRequest, ViewMappingSuggestion,
    ViewColumnMappingResponse, ViewMappingsListResponse, PropagateMetadataResponse,
    ViewSummaryItem, ViewSummaryListResponse,
    DimensionFamilyListResponse, DimensionFamilyItem, DimensionFamilyColumn,
    DimensionFamilyAnalyzeRequest, DimensionFamilyAnalyzeResponse, DimensionFamilySuggestion,
    DimensionFamilyBatchUpdate, DimensionFamilyBatchUpdateResponse,
    OnboardingRequest, InspectRequest, ValidateRequest,
    OnboardingResponse, InspectionSummary, AnalysisSummary, ConfigSummary, ValidationSummary,
    AvailableViewsResponse, AvailableView,
    ApplySqlRequest,
)
from app.services.schema_service import SchemaService
from app.services.admin_config_service import AdminConfigService
from app.services.query_engine import clear_query_cache
from app.config import settings

router = APIRouter()


# ============================================================
# Schema Metadata Endpoints
# ============================================================

@router.get("/schema/columns", response_model=SchemaMetadataListResponse)
def list_schema_columns(
    table_name: Optional[str] = Query(None, description="Filter by table name"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    List all column metadata.
    Admin only.
    """
    query = db.query(SchemaMetadata)
    if table_name:
        query = query.filter(SchemaMetadata.table_name == table_name)

    columns = query.order_by(SchemaMetadata.table_name, SchemaMetadata.column_name).all()

    return SchemaMetadataListResponse(
        columns=[SchemaMetadataResponse.model_validate(c) for c in columns],
        total=len(columns)
    )


@router.get("/schema/columns/{column_id}", response_model=SchemaMetadataResponse)
def get_schema_column(
    column_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Get single column metadata.
    Admin only.
    """
    column = db.query(SchemaMetadata).filter(SchemaMetadata.id == column_id).first()
    if not column:
        raise HTTPException(status_code=404, detail="Column metadata not found")
    return SchemaMetadataResponse.model_validate(column)


@router.post("/schema/columns", response_model=SchemaMetadataResponse, status_code=status.HTTP_201_CREATED)
def create_schema_column(
    data: SchemaMetadataCreate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Add new column metadata.
    Admin only.
    """
    # Check if already exists
    existing = db.query(SchemaMetadata).filter(
        SchemaMetadata.table_name == data.table_name,
        SchemaMetadata.column_name == data.column_name
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Column {data.column_name} in table {data.table_name} already exists"
        )

    column = SchemaMetadata(**data.model_dump())
    db.add(column)
    db.commit()
    db.refresh(column)

    # 🔥 Auto-refresh cache after creating column metadata
    schema_service.refresh_cache()
    clear_query_cache()

    return SchemaMetadataResponse.model_validate(column)


@router.put("/schema/columns/{column_id}", response_model=SchemaMetadataResponse)
def update_schema_column(
    column_id: int,
    data: SchemaMetadataUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Update column metadata.
    Admin only.
    """
    column = db.query(SchemaMetadata).filter(SchemaMetadata.id == column_id).first()
    if not column:
        raise HTTPException(status_code=404, detail="Column metadata not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(column, key, value)

    column.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(column)

    # 🔥 Auto-refresh cache after updating column metadata
    schema_service.refresh_cache()
    clear_query_cache()

    return SchemaMetadataResponse.model_validate(column)


@router.delete("/schema/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schema_column(
    column_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Delete column metadata.
    Admin only.
    """
    column = db.query(SchemaMetadata).filter(SchemaMetadata.id == column_id).first()
    if not column:
        raise HTTPException(status_code=404, detail="Column metadata not found")

    db.delete(column)
    db.commit()

    # 🔥 Auto-refresh cache after deleting column metadata
    schema_service.refresh_cache()
    clear_query_cache()

    return None


# ============================================================
# Semantic Mapping Endpoints
# ============================================================

@router.get("/mappings", response_model=SemanticMappingListResponse)
def list_semantic_mappings(
    keyword_type: Optional[str] = Query(None, description="Filter by type (abbreviation, term, synonym)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    context_name: Optional[str] = Query(None, description="Filter by context (None=all, 'revenue', 'transfer price', etc.)"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    List all semantic mappings.
    Admin only.
    """
    query = db.query(SchemaSemanticMapping)
    if keyword_type:
        query = query.filter(SchemaSemanticMapping.keyword_type == keyword_type)
    if is_active is not None:
        query = query.filter(SchemaSemanticMapping.is_active == is_active)
    if context_name is not None:
        if context_name == "global":
            # Show only global mappings (context_name IS NULL)
            query = query.filter(SchemaSemanticMapping.context_name.is_(None))
        else:
            # Show mappings for this specific context only
            query = query.filter(SchemaSemanticMapping.context_name == context_name)

    mappings = query.order_by(SchemaSemanticMapping.priority.desc(), SchemaSemanticMapping.keyword).all()

    return SemanticMappingListResponse(
        mappings=[SemanticMappingResponse.model_validate(m) for m in mappings],
        total=len(mappings)
    )


@router.get("/mappings/{mapping_id}", response_model=SemanticMappingResponse)
def get_semantic_mapping(
    mapping_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Get single semantic mapping.
    Admin only.
    """
    mapping = db.query(SchemaSemanticMapping).filter(SchemaSemanticMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Semantic mapping not found")
    return SemanticMappingResponse.model_validate(mapping)


@router.post("/mappings", response_model=SemanticMappingResponse, status_code=status.HTTP_201_CREATED)
def create_semantic_mapping(
    data: SemanticMappingCreate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Create semantic mapping.
    Admin only.
    """
    # Check if keyword already exists
    existing = db.query(SchemaSemanticMapping).filter(
        SchemaSemanticMapping.keyword == data.keyword
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Keyword '{data.keyword}' already exists"
        )

    mapping = SchemaSemanticMapping(**data.model_dump())
    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    # 🔥 Auto-refresh cache after creating new mapping
    schema_service.refresh_cache()
    clear_query_cache()

    return SemanticMappingResponse.model_validate(mapping)


@router.put("/mappings/{mapping_id}", response_model=SemanticMappingResponse)
def update_semantic_mapping(
    mapping_id: int,
    data: SemanticMappingUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Update semantic mapping.
    Admin only.
    """
    mapping = db.query(SchemaSemanticMapping).filter(SchemaSemanticMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Semantic mapping not found")

    update_data = data.model_dump(exclude_unset=True)

    # Check keyword uniqueness if being updated
    if 'keyword' in update_data and update_data['keyword'] != mapping.keyword:
        existing = db.query(SchemaSemanticMapping).filter(
            SchemaSemanticMapping.keyword == update_data['keyword']
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Keyword '{update_data['keyword']}' already exists"
            )

    for key, value in update_data.items():
        setattr(mapping, key, value)

    mapping.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(mapping)

    # 🔥 Auto-refresh cache after updating mapping
    schema_service.refresh_cache()
    clear_query_cache()

    return SemanticMappingResponse.model_validate(mapping)


@router.delete("/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_semantic_mapping(
    mapping_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Delete semantic mapping.
    Admin only.
    """
    mapping = db.query(SchemaSemanticMapping).filter(SchemaSemanticMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Semantic mapping not found")

    db.delete(mapping)
    db.commit()

    # 🔥 Auto-refresh cache after deleting mapping
    schema_service.refresh_cache()
    clear_query_cache()

    return None


# ============================================================
# Business Rules Endpoints
# ============================================================

@router.get("/rules", response_model=BusinessRuleListResponse)
def list_business_rules(
    severity: Optional[str] = Query(None, description="Filter by severity (error, warning, info)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    List all business rules.
    Admin only.
    """
    query = db.query(SchemaBusinessRule)
    if severity:
        query = query.filter(SchemaBusinessRule.severity == severity)
    if is_active is not None:
        query = query.filter(SchemaBusinessRule.is_active == is_active)

    rules = query.order_by(
        SchemaBusinessRule.severity,
        SchemaBusinessRule.rule_code
    ).all()

    return BusinessRuleListResponse(
        rules=[BusinessRuleResponse.model_validate(r) for r in rules],
        total=len(rules)
    )


@router.get("/rules/{rule_id}", response_model=BusinessRuleResponse)
def get_business_rule(
    rule_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Get single business rule.
    Admin only.
    """
    rule = db.query(SchemaBusinessRule).filter(SchemaBusinessRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Business rule not found")
    return BusinessRuleResponse.model_validate(rule)


@router.post("/rules", response_model=BusinessRuleResponse, status_code=status.HTTP_201_CREATED)
def create_business_rule(
    data: BusinessRuleCreate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Create new business rule.
    Admin only.
    """
    # Check if rule_code already exists
    existing = db.query(SchemaBusinessRule).filter(
        SchemaBusinessRule.rule_code == data.rule_code
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Rule code '{data.rule_code}' already exists"
        )

    rule = SchemaBusinessRule(**data.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)

    # 🔥 Auto-refresh cache after creating business rule
    schema_service.refresh_cache()
    clear_query_cache()

    return BusinessRuleResponse.model_validate(rule)


@router.put("/rules/{rule_id}", response_model=BusinessRuleResponse)
def update_business_rule(
    rule_id: int,
    data: BusinessRuleUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Update business rule.
    Admin only.
    """
    rule = db.query(SchemaBusinessRule).filter(SchemaBusinessRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Business rule not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)

    rule.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule)

    # 🔥 Auto-refresh cache after updating business rule
    schema_service.refresh_cache()
    clear_query_cache()

    return BusinessRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business_rule(
    rule_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Delete business rule.
    Admin only.
    """
    rule = db.query(SchemaBusinessRule).filter(SchemaBusinessRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Business rule not found")

    db.delete(rule)
    db.commit()

    # 🔥 Auto-refresh cache after deleting business rule
    schema_service.refresh_cache()
    clear_query_cache()

    return None


@router.post("/rules/{rule_id}/toggle", response_model=BusinessRuleResponse)
def toggle_business_rule(
    rule_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    schema_service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Toggle business rule active status.
    Admin only.
    """
    rule = db.query(SchemaBusinessRule).filter(SchemaBusinessRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Business rule not found")

    rule.is_active = not rule.is_active
    rule.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule)

    # 🔥 Auto-refresh cache after toggling business rule
    schema_service.refresh_cache()
    clear_query_cache()

    return BusinessRuleResponse.model_validate(rule)


# ============================================================
# Golden Examples Endpoints
# ============================================================

@router.get("/golden-examples", response_model=GoldenExampleListResponse)
def list_golden_examples(
    category: Optional[str] = Query(None, description="Filter by category"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    List all golden examples.
    Admin only.
    """
    query = db.query(GoldenExample)
    if category:
        query = query.filter(GoldenExample.category == category)
    if is_active is not None:
        query = query.filter(GoldenExample.is_active == is_active)

    total = query.count()
    examples = query.order_by(
        GoldenExample.usage_count.desc(),
        GoldenExample.created_at.desc()
    ).offset(offset).limit(limit).all()

    # Get distinct categories
    categories = db.query(GoldenExample.category).distinct().filter(
        GoldenExample.category.isnot(None)
    ).all()
    category_list = [c[0] for c in categories if c[0]]

    return GoldenExampleListResponse(
        examples=[GoldenExampleResponse.model_validate(e) for e in examples],
        total=total,
        categories=category_list
    )


@router.get("/golden-examples/categories", response_model=List[str])
def list_golden_example_categories(
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    List all golden example categories.
    Admin only.
    """
    categories = db.query(GoldenExample.category).distinct().filter(
        GoldenExample.category.isnot(None)
    ).all()
    return [c[0] for c in categories if c[0]]


@router.get("/golden-examples/{example_id}", response_model=GoldenExampleResponse)
def get_golden_example(
    example_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Get single golden example.
    Admin only.
    """
    example = db.query(GoldenExample).filter(GoldenExample.id == example_id).first()
    if not example:
        raise HTTPException(status_code=404, detail="Golden example not found")
    return GoldenExampleResponse.model_validate(example)


@router.post("/golden-examples", response_model=GoldenExampleResponse, status_code=status.HTTP_201_CREATED)
def create_golden_example(
    data: GoldenExampleCreate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    ai_service: AIService = Depends(deps.get_ai_service)
):
    """
    Create golden example manually.
    Admin only.
    Also trains Vanna (Vector Store).
    """
    example = GoldenExample(
        **data.model_dump(),
        added_by=current_user.id
    )
    db.add(example)
    db.commit()
    db.refresh(example)
    
    # Sync with Vanna (Train)
    if example.is_active:
        ai_service.train(question=example.question_pattern, sql_query=example.expected_sql)
        
    clear_query_cache()
    return GoldenExampleResponse.model_validate(example)


@router.put("/golden-examples/{example_id}", response_model=GoldenExampleResponse)
def update_golden_example(
    example_id: int,
    data: GoldenExampleUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    ai_service: AIService = Depends(deps.get_ai_service)
):
    """
    Update golden example.
    Admin only.
    Also retrains Vanna if active.
    """
    example = db.query(GoldenExample).filter(GoldenExample.id == example_id).first()
    if not example:
        raise HTTPException(status_code=404, detail="Golden example not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(example, key, value)

    db.commit()
    db.refresh(example)
    
    # Sync with Vanna (Train)
    # Note: Vanna training is additive. Updating here just adds a new pair.
    # To fully "update" in Vanna (remove old), we'd need to re-index or use IDs, 
    # but Vanna legacy uses simple vector addition. Adding the correct one is usually enough to override semantic search.
    if example.is_active:
        ai_service.train(question=example.question_pattern, sql_query=example.expected_sql)

    clear_query_cache()
    return GoldenExampleResponse.model_validate(example)


@router.delete("/golden-examples/{example_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_golden_example(
    example_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Delete golden example.
    Admin only.
    Note: Does NOT remove from Vanna Vector DB (Vanna legacy doesn't support granular delete easily).
    Full re-sync is recommended if many deletions occur.
    """
    example = db.query(GoldenExample).filter(GoldenExample.id == example_id).first()
    if not example:
        raise HTTPException(status_code=404, detail="Golden example not found")

    db.delete(example)
    db.commit()
    clear_query_cache()
    return None



# ============================================================
# Schema Context Endpoints
# ============================================================

@router.get("/contexts", response_model=SchemaContextListResponse)
def list_contexts(
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service)
):
    """
    List all schema contexts.
    Admin only.
    """
    contexts = service.get_all_contexts()
    
    return SchemaContextListResponse(
        contexts=[SchemaContextResponse.model_validate(c) for c in contexts],
        total=len(contexts)
    )

@router.post("/contexts", response_model=SchemaContextResponse, status_code=status.HTTP_201_CREATED)
def create_context(
    data: SchemaContextCreate,
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Create new schema context.
    Admin only.
    """
    try:
        context = service.create_context(data.model_dump())
        clear_query_cache()
        return SchemaContextResponse.model_validate(context)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/contexts/{context_id}", response_model=SchemaContextResponse)
def update_context(
    context_id: int,
    data: SchemaContextUpdate,
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Update schema context.
    Admin only.
    """
    try:
        context = service.update_context(context_id, data.model_dump(exclude_unset=True))
        if not context:
            raise HTTPException(status_code=404, detail="Context not found")
        clear_query_cache()
        return SchemaContextResponse.model_validate(context)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/contexts/{context_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_context(
    context_id: int,
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Delete schema context.
    Admin only.
    """
    service.delete_context(context_id)
    clear_query_cache()
    return None


# ============================================================
# View Builder Endpoints
# ============================================================

@router.get("/schema/tables", response_model=List[str])
def list_tables(
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service)
):
    """
    List all tables available for view creation.
    (Excludes system tables)
    """
    return service.get_all_tables()

@router.post("/schema/views", status_code=status.HTTP_201_CREATED)
def create_view(
    data: ViewCreateRequest,
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Create a new view from a source table.
    """
    try:
        mapping_dicts = [m.model_dump() for m in data.mapping]
        service.create_custom_view(
            view_name=data.view_name,
            source_table=data.source_table,
            mapping=mapping_dicts
        )
        clear_query_cache()
        return {"status": "success", "message": f"View {data.view_name} created with column mappings and metadata propagated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create view: {str(e)}")

@router.get("/schema/tables/{table_name}/suggest-mapping", response_model=List[ViewMappingSuggestion])
async def suggest_view_mapping(
    table_name: str,
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
    ai_service: AIService = Depends(deps.get_ai_service)
):
    """
    Get AI-powered mapping suggestions for a table.
    """
    try:
        # 1. Get Schema Info
        columns = service.get_table_info(table_name)

        # 2. Get Sample Values (for better context)
        samples = service.get_sample_values(table_name)

        # 3. Call AI Service (await async method)
        suggestions_data = await ai_service.suggest_mappings(columns, samples)
        
        # 4. Convert to Response Model
        suggestions = []
        for s in suggestions_data:
            suggestions.append(ViewMappingSuggestion(
                col=s.get('col'),
                suggested_alias=s.get('alias'),
                reason=s.get('reason')
            ))
            
        return suggestions
        
    except Exception as e:
        # Fallback if AI fails (though AI Service handles fallback too)
        columns = service.get_table_info(table_name)
        return [
            ViewMappingSuggestion(
                col=col['name'],
                suggested_alias=col['name'].lower(),
                reason=f"Fallback error: {str(e)}"
            ) for col in columns
        ]

# ============================================================
# View Column Mapping Endpoints
# ============================================================

@router.get("/schema/views/summary", response_model=ViewSummaryListResponse)
def list_views_summary(
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service)
):
    """List all views with column mapping summary (mapping count, metadata coverage)."""
    views = service.list_views_with_mappings()
    return ViewSummaryListResponse(
        views=[ViewSummaryItem(**v) for v in views],
        total=len(views)
    )

@router.get("/schema/views/{view_name}/mappings", response_model=ViewMappingsListResponse)
def get_view_mappings(
    view_name: str,
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service)
):
    """Get column mappings for a view (view column → source table column)."""
    mappings = service.get_view_column_mappings(view_name)
    return ViewMappingsListResponse(
        view_name=view_name,
        mappings=[ViewColumnMappingResponse(**m) for m in mappings],
        total=len(mappings)
    )

@router.post("/schema/views/{view_name}/propagate-metadata", response_model=PropagateMetadataResponse)
def propagate_view_metadata(
    view_name: str,
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service)
):
    """Propagate metadata from source table(s) to a view using saved column mappings."""
    result = service.propagate_metadata_to_view(view_name)
    missing = result.get("missing_columns", [])
    msg = f"Propagated: {result['created']} created, {result['updated']} updated, {result.get('skipped', 0)} skipped"
    if missing:
        msg += f". {len(missing)} columns have no source metadata: {', '.join(m['view_column'] for m in missing)}"
    return PropagateMetadataResponse(
        view_name=view_name,
        created=result["created"],
        updated=result["updated"],
        skipped=result.get("skipped", 0),
        missing_columns=missing,
        message=msg,
    )

# ============================================================
# Dimension Family Endpoints
# ============================================================

@router.get("/schema/dimension-families", response_model=DimensionFamilyListResponse)
def get_dimension_families(
    table_name: str = Query(..., description="Table name to get families for"),
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service)
):
    """Get merged dimension families (auto-detect + DB overrides) with source tracking."""
    families_data = service.get_dimension_families_with_source(table_name)
    families = [
        DimensionFamilyItem(
            family_name=f["family_name"],
            columns=[DimensionFamilyColumn(**c) for c in f["columns"]],
            source=f["source"],
        )
        for f in families_data
    ]
    return DimensionFamilyListResponse(
        table_name=table_name,
        families=families,
        total=len(families),
    )


@router.post("/schema/dimension-families/analyze", response_model=DimensionFamilyAnalyzeResponse)
async def analyze_dimension_families(
    request: DimensionFamilyAnalyzeRequest,
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service),
    ai_service: AIService = Depends(deps.get_ai_service)
):
    """LLM analyzes columns + sample values and suggests dimension families (preview only)."""
    import json as _json, re as _re

    columns = service.get_table_info(request.table_name)
    samples = service.get_sample_values(request.table_name)

    column_info = []
    for col in columns:
        name = col["name"]
        sample_vals = samples.get(name, [])[:3]
        column_info.append(f"- {name} ({col['type']}): {sample_vals}")

    column_text = "\n".join(column_info)

    prompt = f"""วิเคราะห์คอลัมน์ในตาราง "{request.table_name}" แล้วจัดกลุ่ม Dimension Family
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
```"""

    try:
        result = await ai_service.provider.generate_content(
            prompt,
            system_prompt="คุณเป็น data analyst ที่เชี่ยวชาญการจัดกลุ่มคอลัมน์"
        )

        json_match = _re.search(r'```json\s*(\{.*?\})\s*```', result, _re.DOTALL)
        if json_match:
            parsed = _json.loads(json_match.group(1))
        else:
            parsed = _json.loads(result)

        suggested = [
            DimensionFamilySuggestion(family_name=f["family_name"], columns=f["columns"])
            for f in parsed.get("families", [])
        ]
        reasoning = parsed.get("reasoning", "")
    except Exception as e:
        suggested = []
        reasoning = f"LLM analysis failed: {str(e)}"

    return DimensionFamilyAnalyzeResponse(
        table_name=request.table_name,
        suggested_families=suggested,
        llm_reasoning=reasoning,
        provider_used=getattr(ai_service.provider, "name", "unknown"),
    )


def _ensure_metadata_rows(db: Session, table_name: str, column_names: list, service: SchemaService):
    """Ensure schema_metadata rows exist for given columns (creates missing ones).

    Views often have no metadata rows yet — this creates minimal rows so
    dimension_group can be saved.
    """
    existing = {
        row.column_name
        for row in db.query(SchemaMetadata.column_name).filter(
            SchemaMetadata.table_name == table_name
        ).all()
    }
    # Get type info from inspector
    col_types = {}
    try:
        for col in service.get_table_info(table_name):
            col_types[col["name"]] = col.get("type", "TEXT")
    except Exception:
        pass

    for col_name in column_names:
        if col_name not in existing:
            db.add(SchemaMetadata(
                table_name=table_name,
                column_name=col_name,
                data_type=col_types.get(col_name, "TEXT"),
            ))
    db.flush()


@router.put("/schema/dimension-families", response_model=DimensionFamilyBatchUpdateResponse)
def batch_update_dimension_families(
    request: DimensionFamilyBatchUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    service: SchemaService = Depends(deps.get_schema_service)
):
    """Batch save dimension_group assignments to DB."""
    # Ensure metadata rows exist for all columns being updated
    col_names = [a.column_name for a in request.assignments]
    _ensure_metadata_rows(db, request.table_name, col_names, service)

    updated = 0
    for assignment in request.assignments:
        row = db.query(SchemaMetadata).filter(
            SchemaMetadata.table_name == request.table_name,
            SchemaMetadata.column_name == assignment.column_name,
        ).first()
        if row:
            row.dimension_group = assignment.dimension_group
            updated += 1

    db.commit()

    # Return updated families
    families_data = service.get_dimension_families_with_source(request.table_name)
    families = [
        DimensionFamilyItem(
            family_name=f["family_name"],
            columns=[DimensionFamilyColumn(**c) for c in f["columns"]],
            source=f["source"],
        )
        for f in families_data
    ]
    return DimensionFamilyBatchUpdateResponse(updated_count=updated, families=families)


@router.post("/schema/dimension-families/auto-populate", response_model=DimensionFamilyBatchUpdateResponse)
def auto_populate_dimension_families(
    table_name: str = Query(..., description="Table/view name"),
    overwrite: bool = Query(False, description="Overwrite existing DB assignments"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
    service: SchemaService = Depends(deps.get_schema_service)
):
    """Run auto-detect and save results to DB."""
    from app.services.dimension_detector import detect_families

    columns = service.get_table_info(table_name)
    all_col_names = [c["name"] for c in columns]
    auto_families = detect_families(all_col_names)

    # Ensure metadata rows exist for all columns in detected families
    all_family_cols = [col for cols in auto_families.values() for col in cols]
    _ensure_metadata_rows(db, table_name, all_family_cols, service)

    updated = 0
    for family_name, cols in auto_families.items():
        for col_name in cols:
            row = db.query(SchemaMetadata).filter(
                SchemaMetadata.table_name == table_name,
                SchemaMetadata.column_name == col_name,
            ).first()
            if row:
                if overwrite or not row.dimension_group:
                    row.dimension_group = family_name
                    updated += 1

    db.commit()

    families_data = service.get_dimension_families_with_source(table_name)
    families = [
        DimensionFamilyItem(
            family_name=f["family_name"],
            columns=[DimensionFamilyColumn(**c) for c in f["columns"]],
            source=f["source"],
        )
        for f in families_data
    ]
    return DimensionFamilyBatchUpdateResponse(updated_count=updated, families=families)


# ============================================================
# Refresh Cache Endpoint
# ============================================================

@router.post("/refresh-cache", response_model=dict)
def refresh_schema_cache(
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Refresh schema cache after metadata updates.
    Admin only.
    """
    from app.services.schema_service import SchemaService
    from app.db.session import config_engine, business_engine
    schema_service = SchemaService(db_engine=config_engine, business_engine=business_engine)
    schema_service.refresh_cache()

    # Also clear query result cache
    from app.services.query_engine import clear_query_cache
    clear_query_cache()

    return {
        "status": "success",
        "message": "Schema cache refreshed and query cache cleared. Changes take effect immediately."
    }


# ============================================================
# Dashboard Stats Endpoint
# ============================================================

from app.schemas.admin_schemas import DashboardStatsResponse

@router.get("/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(
    current_user: User = Depends(deps.require_admin),
    config_db: Session = Depends(deps.get_config_db),
    app_db: Session = Depends(deps.get_db),
):
    """
    Get dashboard statistics.
    Admin only. Queries both app DB (users) and config DB (mappings, rules).
    """
    total_users = app_db.query(User).count()
    total_mappings = config_db.query(SchemaSemanticMapping).count()
    total_rules = config_db.query(SchemaBusinessRule).count()
    total_columns = config_db.query(SchemaMetadata).count()

    return DashboardStatsResponse(
        total_users=total_users,
        total_mappings=total_mappings,
        total_rules=total_rules,
        total_columns=total_columns
    )


# ============================================================
# Sync Brain Endpoints
# ============================================================

@router.post("/sync-brain", response_model=dict)
def sync_brain_knowledge(
    current_user: User = Depends(deps.require_admin),
    service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Trigger Vanna Brain Sync (Retrain Vector DB).
    Admin only.
    """
    try:
        from app.services.vanna_service import VannaService
        vanna = VannaService(config={
            "path": settings.VANNA_CHROMA_PATH,
            "distance_threshold": settings.VANNA_DISTANCE_THRESHOLD
        })
        vanna.sync_brain(service)
        return {"status": "success", "message": "Brain sync completed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear-query-cache", response_model=dict)
def clear_query_cache_endpoint(
    current_user: User = Depends(deps.require_admin),
):
    """
    Clear the in-memory query result cache.
    Use after updating golden examples, business rules, or schema changes
    to ensure fresh SQL generation on next query.
    """
    from app.services.query_engine import clear_query_cache
    cleared = clear_query_cache()
    return {"status": "success", "entries_cleared": cleared}


# ============================================================
# AI Configuration Endpoints
# ============================================================

@router.get("/config/ai", response_model=dict)
def get_ai_config(
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Get complete AI configuration (providers, models, etc).
    Admin only.

    Returns config with fallback to .env if database not configured.
    """
    config_service = AdminConfigService()  # Uses config DB
    ai_config = config_service.get_ai_config()
    feature_flags = config_service.get_feature_flags()

    return {
        "ai": ai_config,
        "features": feature_flags,
        "fallback_note": "Values shown here may come from database (priority 1) or .env file (priority 2)"
    }


@router.put("/config/ai", response_model=dict)
def update_ai_config(
    config_update: dict,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Update AI configuration.
    Admin only.

    Request body example:
    {
        "default_provider": "matcha",
        "claude_enabled": true,
        "gemini_enabled": true,
        "matcha_enabled": true,
        "claude_model": "claude-sonnet-4-5-20250929",
        "gemini_model": "gemini-3-flash-preview",
        "matcha_model": "gpt-4.1",
        "matcha_api_url": "https://aigateway.ntictsolution.com/v1/chat/completions"
    }
    """
    config_service = AdminConfigService()  # Uses config DB

    success = config_service.update_ai_config(
        updates=config_update,
        updated_by=current_user.email
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update configuration")

    # Clear cache to reflect changes
    config_service.clear_cache()

    return {
        "status": "success",
        "message": "AI configuration updated successfully",
        "updated_by": current_user.email
    }


@router.get("/config/ai/providers", response_model=List[dict])
def get_active_providers(
    db: Session = Depends(deps.get_config_db)
):
    """
    Get list of ACTIVE AI providers (enabled by admin).

    PUBLIC endpoint - called by frontend ModelSelector.
    Users can only see and select providers that admin has enabled.

    Returns:
    [
        {
            "id": "matcha",
            "name": "Matcha",
            "display_name": "Matcha (NT Gateway)",
            "model": "gpt-4.1",
            "icon": "leaf",
            "is_default": true
        },
        ...
    ]
    """
    config_service = AdminConfigService()  # Uses config DB
    providers = config_service.get_active_providers()

    return providers


@router.get("/config/ai/models/{provider}", response_model=List[str])
def get_available_models(
    provider: str,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Get available models for a specific provider.
    Admin only.

    Args:
        provider: Provider name (claude, gemini, matcha)

    Returns:
        List of model names
    """
    if provider not in ["claude", "gemini", "matcha"]:
        raise HTTPException(status_code=400, detail="Invalid provider")

    config_service = AdminConfigService()  # Uses config DB
    models = config_service.get_available_models(provider)

    return models


@router.get("/config/features", response_model=dict)
def get_feature_flags(
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Get all feature flags.
    Admin only.
    """
    config_service = AdminConfigService()  # Uses config DB
    return config_service.get_feature_flags()


@router.post("/config/features/{feature_name}/toggle", response_model=dict)
def toggle_feature_flag(
    feature_name: str,
    enabled: bool,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Toggle a feature flag.
    Admin only.

    Args:
        feature_name: Feature to toggle (rag_enabled, auto_context_detection, debug_mode, etc)
        enabled: Enable or disable
    """
    config_service = AdminConfigService()  # Uses config DB

    success = config_service.toggle_feature(
        feature_name=feature_name,
        enabled=enabled,
        updated_by=current_user.email
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to toggle feature")

    return {
        "status": "success",
        "feature": feature_name,
        "enabled": enabled,
        "updated_by": current_user.email
    }


@router.post("/config/cache/clear", response_model=dict)
def clear_config_cache(
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Clear configuration cache.
    Admin only.

    Use this after making direct database changes.
    """
    config_service = AdminConfigService()  # Uses config DB
    config_service.clear_cache()

    return {
        "status": "success",
        "message": "Configuration cache cleared"
    }


@router.post("/config/rebuild-keyword-index", response_model=dict)
def rebuild_keyword_index(
    current_user: User = Depends(deps.require_admin),
    schema_service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Rebuild keyword value index for smart value lookup.
    Scans all searchable columns and builds keyword → column/value mappings.
    Admin only.
    """
    total = 0

    # Build index for ALL active contexts from DB (no hardcode)
    try:
        contexts = schema_service.get_all_contexts()
        for ctx in contexts:
            ctx_name = ctx.get("name", "")
            main_view = ctx.get("main_view", "")
            if ctx_name and main_view:
                try:
                    count = schema_service.build_keyword_index(ctx_name, main_view)
                    total += count
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Failed to build index for {ctx_name}: {e}")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to get contexts for index rebuild: {e}")

    return {
        "status": "success",
        "message": f"Keyword index rebuilt: {total} entries",
        "total_entries": total
    }


# ============================================================
# AI Provider Management Endpoints
# ============================================================

@router.get("/providers", response_model=List[dict])
def list_providers(
    include_inactive: bool = Query(False, description="Include inactive providers"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Get all AI providers.
    Admin only.
    """
    config_service = AdminConfigService()  # Uses config DB
    providers = config_service.get_all_providers(include_inactive=include_inactive)

    return providers


@router.post("/providers", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_provider(
    data: dict,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Create a new AI provider.
    Admin only.

    Request body:
    {
        "id": "openai",
        "name": "OpenAI",
        "display_name": "OpenAI (Direct)",
        "icon": "flash",
        "api_key_env_var": "OPENAI_API_KEY",
        "description": "OpenAI models",
        "priority": 15
    }
    """
    config_service = AdminConfigService()  # Uses config DB

    success = config_service.create_provider(
        provider_id=data.get("id"),
        name=data.get("name"),
        display_name=data.get("display_name"),
        icon=data.get("icon", "bulb"),
        api_key_env_var=data.get("api_key_env_var"),
        description=data.get("description"),
        priority=data.get("priority", 0)
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to create provider")

    return {"status": "success", "message": "Provider created"}


@router.put("/providers/{provider_id}", response_model=dict)
def update_provider(
    provider_id: str,
    data: dict,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Update an existing AI provider.
    Admin only.
    """
    config_service = AdminConfigService()  # Uses config DB

    success = config_service.update_provider(
        provider_id=provider_id,
        name=data.get("name"),
        display_name=data.get("display_name"),
        icon=data.get("icon"),
        is_active=data.get("is_active"),
        is_default=data.get("is_default"),
        description=data.get("description"),
        priority=data.get("priority")
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update provider")

    return {"status": "success", "message": "Provider updated"}


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(
    provider_id: str,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Delete an AI provider (CASCADE deletes models).
    Admin only.
    """
    config_service = AdminConfigService()  # Uses config DB

    success = config_service.delete_provider(provider_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete provider")

    return None


# ============================================================
# AI Model Management Endpoints
# ============================================================

@router.get("/providers/{provider_id}/models", response_model=List[dict])
def list_models(
    provider_id: str,
    include_inactive: bool = Query(False, description="Include inactive models"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Get all models for a provider.
    Admin only.
    """
    config_service = AdminConfigService()  # Uses config DB
    models = config_service.get_models_by_provider(provider_id, include_inactive=include_inactive)

    return models


@router.post("/providers/{provider_id}/models", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_model(
    provider_id: str,
    data: dict,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Create a new AI model for a provider.
    Admin only.

    Request body:
    {
        "model_id": "gpt-4o-mini",
        "display_name": "GPT-4o Mini",
        "is_default": false,
        "context_window": 128000,
        "supports_vision": true,
        "description": "Smaller, faster GPT-4o",
        "priority": 5
    }
    """
    config_service = AdminConfigService()  # Uses config DB

    success = config_service.create_model(
        provider_id=provider_id,
        model_id=data.get("model_id"),
        display_name=data.get("display_name"),
        is_default=data.get("is_default", False),
        context_window=data.get("context_window"),
        supports_vision=data.get("supports_vision", False),
        description=data.get("description"),
        priority=data.get("priority", 0),
        tier=data.get("tier", "default")
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to create model")

    return {"status": "success", "message": "Model created"}


@router.put("/models/{model_id}", response_model=dict)
def update_model(
    model_id: int,
    data: dict,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Update an existing AI model.
    Admin only.
    """
    config_service = AdminConfigService()  # Uses config DB

    success = config_service.update_model(
        model_pk_id=model_id,
        display_name=data.get("display_name"),
        is_active=data.get("is_active"),
        is_default=data.get("is_default"),
        context_window=data.get("context_window"),
        supports_vision=data.get("supports_vision"),
        description=data.get("description"),
        priority=data.get("priority"),
        tier=data.get("tier")
    )

    if not success:
        raise HTTPException(status_code=404, detail="Model not found or update failed")

    return {"status": "success", "message": "Model updated"}


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(
    model_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """
    Delete an AI model.
    Admin only.
    """
    config_service = AdminConfigService()  # Uses config DB

    success = config_service.delete_model(model_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete model")

    return None


# ============================================================
# Hierarchy Management Endpoints
# ============================================================

from fastapi import UploadFile, File
from app.services.hierarchy_service import hierarchy_service
from app.schemas.hierarchy_schemas import (
    HierarchyLevelCreate, HierarchyLevelUpdate, HierarchyLevelResponse,
    HierarchyValueCreate, HierarchyValueUpdate, HierarchyValueResponse,
    HierarchyContextSummary, HierarchySearchResult,
    HierarchyDiff, HierarchyExtractResult, UnmatchedKeyword,
)


# --- Public (used by AI pipeline) ---

@router.get("/hierarchy/{context_name}/search", response_model=List[HierarchySearchResult])
def search_hierarchy(
    context_name: str,
    q: str = Query(..., min_length=1, description="Search keyword"),
    limit: int = Query(10, le=50),
):
    """Search hierarchy values by alias match. Public — used by AI pipeline."""
    return hierarchy_service.search_aliases(context_name, q, limit)


# --- Admin: Context & Level management ---

@router.get("/hierarchy", response_model=List[HierarchyContextSummary])
def list_hierarchy_contexts(
    current_user: User = Depends(deps.require_admin),
):
    """List all hierarchy contexts with summary."""
    return hierarchy_service.list_contexts()


@router.get("/hierarchy/{context_name}/levels", response_model=List[HierarchyLevelResponse])
def get_hierarchy_levels(
    context_name: str,
    current_user: User = Depends(deps.require_admin),
):
    """Get hierarchy levels for a context."""
    return hierarchy_service.get_levels(context_name)


@router.post("/hierarchy/{context_name}/levels")
def create_hierarchy_level(
    context_name: str,
    body: HierarchyLevelCreate,
    current_user: User = Depends(deps.require_admin),
):
    """Create or update a hierarchy level."""
    result = hierarchy_service.upsert_level(context_name, body.level, body.model_dump())
    clear_query_cache()
    return result


@router.put("/hierarchy/{context_name}/levels/{level}")
def update_hierarchy_level(
    context_name: str,
    level: int,
    body: HierarchyLevelUpdate,
    current_user: User = Depends(deps.require_admin),
):
    """Update a hierarchy level."""
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    result = hierarchy_service.upsert_level(context_name, level, data)
    clear_query_cache()
    return result


@router.delete("/hierarchy/{context_name}/levels/{level}", status_code=204)
def delete_hierarchy_level(
    context_name: str,
    level: int,
    current_user: User = Depends(deps.require_admin),
):
    """Soft-delete a hierarchy level."""
    hierarchy_service.delete_level(context_name, level)
    clear_query_cache()
    return None


# --- Admin: Value management ---

@router.get("/hierarchy/{context_name}/values")
def get_hierarchy_values(
    context_name: str,
    level: Optional[int] = None,
    parent_value: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    current_user: User = Depends(deps.require_admin),
):
    """Get hierarchy values with filtering and pagination."""
    return hierarchy_service.get_values(context_name, level, parent_value, search, page, page_size)


@router.post("/hierarchy/{context_name}/values")
def create_hierarchy_value(
    context_name: str,
    body: HierarchyValueCreate,
    current_user: User = Depends(deps.require_admin),
):
    """Create a hierarchy value (source='manual')."""
    result = hierarchy_service.create_value(context_name, body.model_dump())
    clear_query_cache()
    return result


@router.put("/hierarchy/values/{value_id}")
def update_hierarchy_value(
    value_id: int,
    body: HierarchyValueUpdate,
    current_user: User = Depends(deps.require_admin),
):
    """Update a hierarchy value."""
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    result = hierarchy_service.update_value(value_id, data)
    clear_query_cache()
    return result


@router.delete("/hierarchy/values/{value_id}", status_code=204)
def delete_hierarchy_value(
    value_id: int,
    current_user: User = Depends(deps.require_admin),
):
    """Soft-delete a hierarchy value."""
    hierarchy_service.delete_value(value_id)
    clear_query_cache()
    return None


# --- Admin: Extract & Sync ---

@router.post("/hierarchy/extract", response_model=List[HierarchyExtractResult])
def extract_hierarchy(
    context_name: Optional[str] = None,
    current_user: User = Depends(deps.require_admin),
):
    """Trigger auto-extract hierarchy from data."""
    result = hierarchy_service.auto_extract(context_name)
    clear_query_cache()
    return result


@router.post("/hierarchy/bootstrap")
def bootstrap_hierarchy(
    context_name: str = Query(..., description="New context name"),
    view_name: str = Query(..., description="View/table to extract from"),
    current_user: User = Depends(deps.require_admin),
):
    """
    Bootstrap a new hierarchy context from scratch.

    Auto-detects hierarchy columns from the view, creates levels, and extracts values.
    No pre-existing config needed — solves the chicken-and-egg problem.
    """
    result = hierarchy_service.bootstrap_from_view(context_name, view_name)
    if "error" in result:
        raise HTTPException(400, result["error"])
    hierarchy_service._invalidate_cache()
    clear_query_cache()
    return result


@router.get("/hierarchy/views")
def list_available_views(
    current_user: User = Depends(deps.require_admin),
):
    """List available views/tables that can be used for hierarchy extraction."""
    return hierarchy_service.get_available_views()


@router.post("/hierarchy/{context_name}/import-csv")
async def import_csv_hierarchy(
    context_name: str,
    file: UploadFile = File(...),
    level: int = Query(..., description="Target hierarchy level"),
    value_column: str = Query(..., description="CSV column containing the value"),
    parent_column: Optional[str] = Query(None, description="CSV column containing the parent value"),
    alias_columns: Optional[str] = Query(None, description="Comma-separated CSV columns to use as aliases"),
    current_user: User = Depends(deps.require_admin),
):
    """
    Import hierarchy values from an uploaded CSV file.

    Flexible: admin specifies which CSV columns map to value, parent, and aliases.
    Works with any CSV format — no hardcoded column expectations.
    """
    import csv, io
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        raise HTTPException(400, "CSV file is empty")

    # Validate columns exist
    csv_columns = list(rows[0].keys())
    if value_column not in csv_columns:
        raise HTTPException(400, f"Column '{value_column}' not found. Available: {csv_columns}")
    if parent_column and parent_column not in csv_columns:
        raise HTTPException(400, f"Column '{parent_column}' not found. Available: {csv_columns}")

    alias_cols = [c.strip() for c in alias_columns.split(",")] if alias_columns else []
    for ac in alias_cols:
        if ac not in csv_columns:
            raise HTTPException(400, f"Alias column '{ac}' not found. Available: {csv_columns}")

    imported = 0
    for row in rows:
        value = (row.get(value_column) or "").strip()
        if not value:
            continue
        parent = (row.get(parent_column) or "").strip() if parent_column else None

        aliases = [value.lower()]
        for ac in alias_cols:
            alias_val = (row.get(ac) or "").strip()
            if alias_val and alias_val.lower() not in aliases:
                aliases.append(alias_val.lower())

        hierarchy_service.create_value(context_name, {
            "level": level, "value": value,
            "parent_value": parent or None,
            "aliases": sorted(aliases),
        })
        imported += 1

    clear_query_cache()
    return {"success": True, "imported": imported, "filename": file.filename}


@router.get("/hierarchy/{context_name}/diff", response_model=HierarchyDiff)
def get_hierarchy_diff(
    context_name: str,
    current_user: User = Depends(deps.require_admin),
):
    """Compare master hierarchy vs actual data — show new/missing values."""
    return hierarchy_service.detect_changes(context_name)


# --- Admin: Unmatched keywords ---

@router.get("/hierarchy/unmatched", response_model=List[UnmatchedKeyword])
def get_unmatched_keywords(
    context_name: Optional[str] = None,
    limit: int = Query(50, le=200),
    current_user: User = Depends(deps.require_admin),
):
    """Get unmatched keywords that AI used LIKE for but had no alias match."""
    return hierarchy_service.get_unmatched_keywords(context_name, limit)


@router.post("/hierarchy/unmatched/{keyword}/resolve")
def resolve_unmatched_keyword(
    keyword: str,
    context_name: str = Query(...),
    current_user: User = Depends(deps.require_admin),
):
    """Mark an unmatched keyword as resolved."""
    hierarchy_service.resolve_unmatched_keyword(keyword, context_name)
    clear_query_cache()
    return {"success": True}


# ============================================================
# Data Warnings Endpoints
# ============================================================

from app.models.schema_models import DataWarningModel
from app.schemas.admin_schemas import (
    DataWarningCreate, DataWarningUpdate, DataWarningResponse, DataWarningListResponse,
)
from app.services.warning_detector import clear_warnings_cache


@router.get("/warnings", response_model=DataWarningListResponse)
def list_data_warnings(
    severity: Optional[str] = Query(None, description="Filter by severity"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    context_name: Optional[str] = Query(None, description="Filter by context"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """List all data warnings. Admin only."""
    query = db.query(DataWarningModel)
    if severity:
        query = query.filter(DataWarningModel.severity == severity)
    if is_active is not None:
        query = query.filter(DataWarningModel.is_active == is_active)
    if context_name:
        query = query.filter(DataWarningModel.context_name == context_name)

    warnings = query.order_by(DataWarningModel.code).all()
    return DataWarningListResponse(
        warnings=[DataWarningResponse.model_validate(w) for w in warnings],
        total=len(warnings),
    )


@router.get("/warnings/{warning_id}", response_model=DataWarningResponse)
def get_data_warning(
    warning_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Get single data warning. Admin only."""
    warning = db.query(DataWarningModel).filter(DataWarningModel.id == warning_id).first()
    if not warning:
        raise HTTPException(status_code=404, detail="Data warning not found")
    return DataWarningResponse.model_validate(warning)


@router.post("/warnings", response_model=DataWarningResponse, status_code=status.HTTP_201_CREATED)
def create_data_warning(
    data: DataWarningCreate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Create new data warning. Admin only."""
    existing = db.query(DataWarningModel).filter(DataWarningModel.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Warning code '{data.code}' already exists")

    warning = DataWarningModel(**data.model_dump())
    db.add(warning)
    db.commit()
    db.refresh(warning)

    clear_warnings_cache()
    return DataWarningResponse.model_validate(warning)


@router.put("/warnings/{warning_id}", response_model=DataWarningResponse)
def update_data_warning(
    warning_id: int,
    data: DataWarningUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Update data warning. Admin only."""
    warning = db.query(DataWarningModel).filter(DataWarningModel.id == warning_id).first()
    if not warning:
        raise HTTPException(status_code=404, detail="Data warning not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(warning, key, value)

    warning.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(warning)

    clear_warnings_cache()
    return DataWarningResponse.model_validate(warning)


@router.delete("/warnings/{warning_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_data_warning(
    warning_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Delete data warning. Admin only."""
    warning = db.query(DataWarningModel).filter(DataWarningModel.id == warning_id).first()
    if not warning:
        raise HTTPException(status_code=404, detail="Data warning not found")

    db.delete(warning)
    db.commit()

    clear_warnings_cache()
    return None


# ============================================================
# Query Complexity Pattern Endpoints
# ============================================================

from app.models.schema_models import QueryComplexityPattern
from app.schemas.admin_schemas import (
    QueryPatternCreate, QueryPatternUpdate, QueryPatternResponse, QueryPatternListResponse,
)
from app.services.query_classifier import clear_patterns_cache


@router.get("/query-patterns", response_model=QueryPatternListResponse)
def list_query_patterns(
    tier: Optional[str] = Query(None, description="Filter by tier (simple/complex)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """List all query complexity patterns. Admin only."""
    query = db.query(QueryComplexityPattern)
    if tier:
        query = query.filter(QueryComplexityPattern.tier == tier)
    if is_active is not None:
        query = query.filter(QueryComplexityPattern.is_active == is_active)

    patterns = query.order_by(QueryComplexityPattern.tier, QueryComplexityPattern.id).all()
    return QueryPatternListResponse(
        patterns=[QueryPatternResponse.model_validate(p) for p in patterns],
        total=len(patterns),
    )


@router.get("/query-patterns/{pattern_id}", response_model=QueryPatternResponse)
def get_query_pattern(
    pattern_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Get single query pattern. Admin only."""
    pattern = db.query(QueryComplexityPattern).filter(QueryComplexityPattern.id == pattern_id).first()
    if not pattern:
        raise HTTPException(status_code=404, detail="Query pattern not found")
    return QueryPatternResponse.model_validate(pattern)


@router.post("/query-patterns", response_model=QueryPatternResponse, status_code=status.HTTP_201_CREATED)
def create_query_pattern(
    data: QueryPatternCreate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Create new query pattern. Admin only."""
    existing = db.query(QueryComplexityPattern).filter(
        QueryComplexityPattern.tier == data.tier,
        QueryComplexityPattern.pattern == data.pattern,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Pattern already exists for tier '{data.tier}'")

    pattern = QueryComplexityPattern(**data.model_dump())
    db.add(pattern)
    db.commit()
    db.refresh(pattern)

    clear_patterns_cache()
    return QueryPatternResponse.model_validate(pattern)


@router.put("/query-patterns/{pattern_id}", response_model=QueryPatternResponse)
def update_query_pattern(
    pattern_id: int,
    data: QueryPatternUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Update query pattern. Admin only."""
    pattern = db.query(QueryComplexityPattern).filter(QueryComplexityPattern.id == pattern_id).first()
    if not pattern:
        raise HTTPException(status_code=404, detail="Query pattern not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(pattern, key, value)

    db.commit()
    db.refresh(pattern)

    clear_patterns_cache()
    return QueryPatternResponse.model_validate(pattern)


@router.delete("/query-patterns/{pattern_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_query_pattern(
    pattern_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),
):
    """Delete query pattern. Admin only."""
    pattern = db.query(QueryComplexityPattern).filter(QueryComplexityPattern.id == pattern_id).first()
    if not pattern:
        raise HTTPException(status_code=404, detail="Query pattern not found")

    db.delete(pattern)
    db.commit()

    clear_patterns_cache()
    return None


# ============================================================
# Query Logs Endpoint
# ============================================================

@router.get("/query-logs")
def get_query_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    context: Optional[str] = None,
    user_id: Optional[int] = None,
    feedback_only: bool = Query(False, description="Only show queries with feedback"),
    thumbs_down_only: bool = Query(False, description="Only show thumbs-down queries"),
    has_error: bool = Query(False, description="Only show queries with errors"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),  # App DB — chat_history, user_feedback
):
    """Get paginated query logs with optional feedback join. Admin only."""
    from app.models.chat import ChatHistory
    from app.models.user import User as UserModel
    from app.models.feedback_models import UserFeedback, FeedbackRating

    # Left join with feedback
    query = db.query(ChatHistory, UserFeedback).outerjoin(
        UserFeedback, ChatHistory.id == UserFeedback.chat_id
    ).order_by(ChatHistory.created_at.desc())

    if date_from:
        try:
            dt = datetime.fromisoformat(date_from)
            query = query.filter(ChatHistory.created_at >= dt)
        except ValueError:
            pass

    if date_to:
        try:
            dt = datetime.fromisoformat(date_to)
            query = query.filter(ChatHistory.created_at <= dt)
        except ValueError:
            pass

    if context:
        query = query.filter(ChatHistory.context_name == context)

    if user_id:
        query = query.filter(ChatHistory.user_id == user_id)

    if feedback_only:
        query = query.filter(UserFeedback.id != None)

    if thumbs_down_only:
        query = query.filter(UserFeedback.rating == FeedbackRating.THUMBS_DOWN)

    if has_error:
        query = query.filter(
            (ChatHistory.generated_sql == None) | (ChatHistory.generated_sql == "")
        )

    total = query.count()
    rows = query.offset(skip).limit(limit).all()

    # Map user IDs to emails
    user_ids = list(set(r[0].user_id for r in rows if r[0].user_id))
    user_map = {}
    if user_ids:
        users = db.query(UserModel).filter(UserModel.id.in_(user_ids)).all()
        user_map = {u.id: u.email for u in users}

    items = []
    for chat, feedback in rows:
        item = {
            "id": chat.id,
            "user_id": chat.user_id,
            "user_email": user_map.get(chat.user_id, "unknown"),
            "question": chat.question,
            "generated_sql": chat.generated_sql,  # Full SQL — not truncated
            "sql_result_summary": (chat.sql_result_summary or "")[:500],
            "ai_response": (chat.ai_response or "")[:300],
            "tokens_used": chat.tokens_used,
            "execution_time_ms": chat.execution_time_ms,
            "context_name": chat.context_name,
            "feedback_rating": chat.feedback_rating,
            "created_at": chat.created_at.isoformat() if chat.created_at else None,
        }
        # Attach feedback details if present
        if feedback:
            item["feedback"] = {
                "id": feedback.id,
                "rating": feedback.rating.value if feedback.rating else None,
                "category": feedback.feedback_category.value if feedback.feedback_category else None,
                "text": feedback.feedback_text,
                "reviewed": feedback.reviewed_at is not None,
            }
        else:
            item["feedback"] = None
        items.append(item)

    return {"total": total, "items": items}


@router.get("/feedback-details/{feedback_id}")
def get_feedback_details(
    feedback_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),  # App DB — user_feedback, chat_history
):
    """Get full feedback details including complete ChatHistory."""
    from app.models.chat import ChatHistory
    from app.models.feedback_models import UserFeedback

    feedback = db.query(UserFeedback).filter(UserFeedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    chat = db.query(ChatHistory).filter(ChatHistory.id == feedback.chat_id).first()

    return {
        "feedback": {
            "id": feedback.id,
            "rating": feedback.rating.value if feedback.rating else None,
            "category": feedback.feedback_category.value if feedback.feedback_category else None,
            "text": feedback.feedback_text,
            "reviewed_at": str(feedback.reviewed_at) if feedback.reviewed_at else None,
            "reviewed_by": feedback.reviewed_by,
            "created_at": str(feedback.created_at) if feedback.created_at else None,
        },
        "chat": {
            "id": chat.id,
            "question": chat.question,
            "generated_sql": chat.generated_sql,
            "sql_result_summary": chat.sql_result_summary,
            "ai_response": chat.ai_response,
            "tokens_used": chat.tokens_used,
            "execution_time_ms": chat.execution_time_ms,
            "context_name": chat.context_name,
            "created_at": chat.created_at.isoformat() if chat.created_at else None,
        } if chat else None,
    }


@router.get("/query-analytics")
def get_query_analytics(
    period: str = Query("7d", description="Period: 7d, 30d, 90d"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),  # App DB — chat_history, user_feedback
):
    """Get aggregated query analytics: error rates, top failures, context distribution."""
    from app.models.chat import ChatHistory
    from app.models.feedback_models import UserFeedback, FeedbackRating
    from datetime import timedelta

    # Parse period
    days_map = {"7d": 7, "30d": 30, "90d": 90}
    days = days_map.get(period, 7)
    since = datetime.utcnow() - timedelta(days=days)

    # Total queries
    total = db.query(ChatHistory).filter(ChatHistory.created_at >= since).count()

    # Errors (no generated SQL)
    errors = db.query(ChatHistory).filter(
        ChatHistory.created_at >= since,
        (ChatHistory.generated_sql == None) | (ChatHistory.generated_sql == "")
    ).count()

    # Thumbs down count
    thumbs_down = db.query(UserFeedback).filter(
        UserFeedback.created_at >= since,
        UserFeedback.rating == FeedbackRating.THUMBS_DOWN,
    ).count()

    # Total feedback
    total_feedback = db.query(UserFeedback).filter(
        UserFeedback.created_at >= since
    ).count()

    # Context distribution
    from sqlalchemy import func
    context_rows = db.query(
        ChatHistory.context_name, func.count(ChatHistory.id)
    ).filter(
        ChatHistory.created_at >= since
    ).group_by(ChatHistory.context_name).all()

    context_distribution = {(ctx or "unknown"): count for ctx, count in context_rows}

    # Feedback category distribution
    category_rows = db.query(
        UserFeedback.feedback_category, func.count(UserFeedback.id)
    ).filter(
        UserFeedback.created_at >= since,
        UserFeedback.rating == FeedbackRating.THUMBS_DOWN,
    ).group_by(UserFeedback.feedback_category).all()

    error_categories = {}
    for cat, count in category_rows:
        cat_name = cat.value if cat else "unspecified"
        error_categories[cat_name] = count

    return {
        "period": period,
        "total_queries": total,
        "error_count": errors,
        "error_rate": round(errors / total, 3) if total > 0 else 0,
        "thumbs_down_count": thumbs_down,
        "thumbs_down_rate": round(thumbs_down / total_feedback, 3) if total_feedback > 0 else 0,
        "total_feedback": total_feedback,
        "context_distribution": context_distribution,
        "error_categories": error_categories,
    }


# ============================================================
# Context Onboarding Endpoints
# ============================================================

def _get_business_db_path() -> str:
    """Get business DB path. Priority: BUSINESS_DB_PATH > DATABASE_URL > fallback."""
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    # 1. Explicit BUSINESS_DB_PATH
    if getattr(settings, 'BUSINESS_DB_PATH', None):
        db_path = settings.BUSINESS_DB_PATH
        if not os.path.isabs(db_path):
            db_path = os.path.join(project_root, db_path)
        return db_path

    # 2. Extract from DATABASE_URL
    db_url = str(getattr(settings, 'DATABASE_URL', ''))
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "")
        if not os.path.isabs(db_path):
            db_path = os.path.join(project_root, db_path)
        return db_path

    # 3. Fallback
    return os.path.join(project_root, "nt_fi_report.sqlite")


@router.get("/contexts/onboard/available-views", response_model=AvailableViewsResponse)
def list_onboardable_views(
    current_user: User = Depends(deps.require_admin),
):
    """List views/tables with their onboarding status."""
    from app.services.context_onboarding import ContextOnboardingService

    db_path = _get_business_db_path()
    service = ContextOnboardingService(db_path)

    try:
        result = service.list_available_views()
        return AvailableViewsResponse(
            unconfigured=[AvailableView(**v) for v in result["unconfigured"]],
            configured=[AvailableView(**v) for v in result["configured"]],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contexts/onboard", response_model=OnboardingResponse)
async def onboard_context(
    request: OnboardingRequest,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """Full context onboarding pipeline: inspect → analyze (LLM) → generate config → (apply)."""
    from app.services.context_onboarding import ContextOnboardingService

    db_path = _get_business_db_path()
    service = ContextOnboardingService(db_path)

    # Phase 1: Inspect
    try:
        inspection = service.inspect(request.view_name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Inspection failed: {str(e)}")

    inspection_summary = InspectionSummary(
        row_count=inspection.row_count,
        columns=len(inspection.columns),
        detected_structure=inspection.detected_structure,
        quality_issues=len(inspection.quality_issues),
    )

    if request.inspect_only:
        return OnboardingResponse(
            status="inspect_only",
            inspection=inspection_summary,
        )

    # Phase 2-3: Analyze + Generate
    try:
        analysis = await service.analyze(
            inspection,
            provider=request.provider,
            model=request.model,
            api_url=request.api_url,
        )
        config = service.generate_config(analysis, view_name=request.view_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

    # Phase 4: Apply
    apply_result = service.apply(config, dry_run=request.dry_run)

    # Phase 5: Validate (only if applied)
    validation_summary = None
    if not request.dry_run:
        try:
            validation = await service.validate(request.view_name)
            validation_summary = ValidationSummary(
                passed=validation.passed,
                results=validation.test_results,
                issues=validation.issues if hasattr(validation, 'issues') else [],
            )
            try:
                from app.db.session import config_engine as _ce, business_engine as _be
                schema_service = SchemaService(db_engine=_ce, business_engine=_be)
                schema_service.refresh_cache()
            except Exception:
                pass
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
    """Lightweight: inspect only (no LLM). Fast."""
    from app.services.context_onboarding import ContextOnboardingService

    db_path = _get_business_db_path()
    service = ContextOnboardingService(db_path)

    try:
        inspection = service.inspect(request.view_name)
        return {"status": "ok", "inspection": inspection.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/contexts/onboard/apply-sql")
async def apply_sql_statements(
    request: ApplySqlRequest,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db)
):
    """Apply pre-generated SQL statements directly (no LLM re-run)."""
    from app.services.context_onboarding import ContextOnboardingService

    if not request.sql_statements:
        raise HTTPException(status_code=400, detail="sql_statements is empty")

    db_path = _get_business_db_path()
    service = ContextOnboardingService(db_path)

    try:
        apply_result = service.apply_sql_statements(request.sql_statements)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Apply failed: {str(e)}")

    # Validate after apply
    validation_summary = None
    try:
        validation = await service.validate(request.view_name)
        validation_summary = {
            "passed": validation.passed,
            "results": validation.test_results,
            "issues": validation.issues if hasattr(validation, 'issues') else [],
        }
        try:
            from app.db.session import config_engine as _ce2, business_engine as _be2
            schema_service = SchemaService(db_engine=_ce2, business_engine=_be2)
            schema_service.refresh_cache()
        except Exception:
            pass
    except Exception:
        pass

    return {
        "status": "applied",
        "apply": apply_result,
        "validation": validation_summary,
    }


@router.post("/contexts/onboard/validate")
async def validate_context(
    request: ValidateRequest,
    current_user: User = Depends(deps.require_admin),
):
    """Validate that config exists for a view."""
    from app.services.context_onboarding import ContextOnboardingService

    db_path = _get_business_db_path()
    service = ContextOnboardingService(db_path)

    try:
        validation = await service.validate(request.view_name)
        return {
            "status": "ok",
            "passed": validation.passed,
            "results": validation.test_results,
            "issues": validation.issues,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# API Key Management (Plan 4B)
# ═══════════════════════════════════════════════════════════

from pydantic import BaseModel as PydanticBaseModel, Field as PydanticField


class APIKeyCreateRequest(PydanticBaseModel):
    name: str = PydanticField(..., description="Human-readable name for the key")
    scopes: str = PydanticField("query", description="Comma-separated scopes: query, admin, full")
    rate_limit_per_minute: int = PydanticField(30, ge=1, le=1000)
    rate_limit_per_day: int = PydanticField(1000, ge=1, le=100000)


class APIKeyResponse(PydanticBaseModel):
    id: int
    key_prefix: str
    name: str
    user_id: int
    scopes: str
    rate_limit_per_minute: int
    rate_limit_per_day: int
    is_active: bool
    last_used_at: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class APIKeyCreateResponse(APIKeyResponse):
    raw_key: str = PydanticField(..., description="Full API key — shown ONCE")


@router.post("/api-keys", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    request: APIKeyCreateRequest,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),  # App DB — api_keys table
):
    """Create a new API key. The raw key is returned ONCE and cannot be retrieved later."""
    from app.services.api_key_service import APIKeyService, KEY_PREFIX
    service = APIKeyService(db)

    raw_key, api_key = service.create_key(
        user_id=current_user.id,
        name=request.name,
        scopes=request.scopes,
        rate_limit_per_minute=request.rate_limit_per_minute,
        rate_limit_per_day=request.rate_limit_per_day,
    )

    return APIKeyCreateResponse(
        id=api_key.id,
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        user_id=api_key.user_id,
        scopes=api_key.scopes,
        rate_limit_per_minute=api_key.rate_limit_per_minute,
        rate_limit_per_day=api_key.rate_limit_per_day,
        is_active=api_key.is_active,
        last_used_at=str(api_key.last_used_at) if api_key.last_used_at else None,
        created_at=str(api_key.created_at) if api_key.created_at else None,
        raw_key=raw_key,
    )


@router.get("/api-keys", response_model=list)
def list_api_keys(
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),  # App DB — api_keys table
):
    """List all API keys for the current user."""
    from app.services.api_key_service import APIKeyService, KEY_PREFIX
    service = APIKeyService(db)
    keys = service.list_keys(user_id=current_user.id)

    return [
        APIKeyResponse(
            id=k.id, key_prefix=k.key_prefix, name=k.name, user_id=k.user_id,
            scopes=k.scopes, rate_limit_per_minute=k.rate_limit_per_minute,
            rate_limit_per_day=k.rate_limit_per_day, is_active=k.is_active,
            last_used_at=str(k.last_used_at) if k.last_used_at else None,
            created_at=str(k.created_at) if k.created_at else None,
        ).model_dump()
        for k in keys
    ]


@router.delete("/api-keys/{key_id}")
def revoke_api_key(
    key_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),  # App DB — api_keys table
):
    """Revoke (soft delete) an API key."""
    from app.services.api_key_service import APIKeyService, KEY_PREFIX
    service = APIKeyService(db)
    success = service.revoke_key(key_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "revoked", "key_id": key_id}


@router.get("/api-keys/{key_id}/usage")
def get_api_key_usage(
    key_id: int,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),  # App DB — api_key_usage table
):
    """Get usage statistics for an API key."""
    from app.services.api_key_service import APIKeyService, KEY_PREFIX
    service = APIKeyService(db)
    return service.get_usage_stats(key_id, days=days)
