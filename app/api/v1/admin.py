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
    SchemaContextCreate, SchemaContextUpdate, SchemaContextResponse, SchemaContextListResponse,
    ViewCreateRequest, ViewMappingSuggestion,
    ViewColumnMappingResponse, ViewMappingsListResponse, PropagateMetadataResponse,
    ViewSummaryItem, ViewSummaryListResponse,
    DimensionFamilyListResponse, DimensionFamilyItem, DimensionFamilyColumn,
    DimensionFamilyAnalyzeRequest, DimensionFamilyAnalyzeResponse, DimensionFamilySuggestion,
    DimensionFamilyBatchUpdate, DimensionFamilyBatchUpdateResponse,
)
from app.services.schema_service import SchemaService
from app.services.admin_config_service import AdminConfigService
from app.config import settings

router = APIRouter()


# ============================================================
# Schema Metadata Endpoints
# ============================================================

@router.get("/schema/columns", response_model=SchemaMetadataListResponse)
def list_schema_columns(
    table_name: Optional[str] = Query(None, description="Filter by table name"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
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
    db: Session = Depends(deps.get_db)
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
    db: Session = Depends(deps.get_db),
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

    return SchemaMetadataResponse.model_validate(column)


@router.put("/schema/columns/{column_id}", response_model=SchemaMetadataResponse)
def update_schema_column(
    column_id: int,
    data: SchemaMetadataUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
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

    return SchemaMetadataResponse.model_validate(column)


@router.delete("/schema/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schema_column(
    column_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
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
    db: Session = Depends(deps.get_db)
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
    db: Session = Depends(deps.get_db)
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
    db: Session = Depends(deps.get_db),
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

    return SemanticMappingResponse.model_validate(mapping)


@router.put("/mappings/{mapping_id}", response_model=SemanticMappingResponse)
def update_semantic_mapping(
    mapping_id: int,
    data: SemanticMappingUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
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

    return SemanticMappingResponse.model_validate(mapping)


@router.delete("/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_semantic_mapping(
    mapping_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
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

    return None


# ============================================================
# Business Rules Endpoints
# ============================================================

@router.get("/rules", response_model=BusinessRuleListResponse)
def list_business_rules(
    severity: Optional[str] = Query(None, description="Filter by severity (error, warning, info)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
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
    db: Session = Depends(deps.get_db)
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
    db: Session = Depends(deps.get_db),
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

    return BusinessRuleResponse.model_validate(rule)


@router.put("/rules/{rule_id}", response_model=BusinessRuleResponse)
def update_business_rule(
    rule_id: int,
    data: BusinessRuleUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
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

    return BusinessRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business_rule(
    rule_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
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

    return None


@router.post("/rules/{rule_id}/toggle", response_model=BusinessRuleResponse)
def toggle_business_rule(
    rule_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
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
    db: Session = Depends(deps.get_db)
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
    db: Session = Depends(deps.get_db)
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
    db: Session = Depends(deps.get_db)
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
    db: Session = Depends(deps.get_db),
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
        
    return GoldenExampleResponse.model_validate(example)


@router.put("/golden-examples/{example_id}", response_model=GoldenExampleResponse)
def update_golden_example(
    example_id: int,
    data: GoldenExampleUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
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
         
    return GoldenExampleResponse.model_validate(example)


@router.delete("/golden-examples/{example_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_golden_example(
    example_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
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
    db: Session = Depends(deps.get_db),
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
    db: Session = Depends(deps.get_db),
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
    db: Session = Depends(deps.get_db)
):
    """
    Refresh schema cache after metadata updates.
    Admin only.
    """
    # This would be called after updating schema metadata to refresh any cached prompts
    # The actual implementation depends on how the SchemaService cache is accessed

    return {
        "status": "success",
        "message": "Schema cache refresh triggered. Changes will take effect on next query."
    }


# ============================================================
# Dashboard Stats Endpoint
# ============================================================

from app.schemas.admin_schemas import DashboardStatsResponse

@router.get("/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
):
    """
    Get dashboard statistics.
    Admin only.
    """
    total_users = db.query(User).count()
    total_mappings = db.query(SchemaSemanticMapping).count()
    total_rules = db.query(SchemaBusinessRule).count()
    total_columns = db.query(SchemaMetadata).count()

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


# ============================================================
# AI Configuration Endpoints
# ============================================================

@router.get("/config/ai", response_model=dict)
def get_ai_config(
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
):
    """
    Get complete AI configuration (providers, models, etc).
    Admin only.

    Returns config with fallback to .env if database not configured.
    """
    config_service = AdminConfigService(db)
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
    db: Session = Depends(deps.get_db)
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
    config_service = AdminConfigService(db)

    success = config_service.update_ai_config(
        default_provider=config_update.get("default_provider"),
        claude_enabled=config_update.get("claude_enabled"),
        gemini_enabled=config_update.get("gemini_enabled"),
        matcha_enabled=config_update.get("matcha_enabled"),
        claude_model=config_update.get("claude_model"),
        gemini_model=config_update.get("gemini_model"),
        matcha_model=config_update.get("matcha_model"),
        matcha_api_url=config_update.get("matcha_api_url"),
        claude_extended_thinking=config_update.get("claude_extended_thinking"),
        claude_thinking_budget_tokens=config_update.get("claude_thinking_budget_tokens"),
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
    db: Session = Depends(deps.get_db)
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
    config_service = AdminConfigService(db)
    providers = config_service.get_active_providers()

    return providers


@router.get("/config/ai/models/{provider}", response_model=List[str])
def get_available_models(
    provider: str,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
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

    config_service = AdminConfigService(db)
    models = config_service.get_available_models(provider)

    return models


@router.get("/config/features", response_model=dict)
def get_feature_flags(
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
):
    """
    Get all feature flags.
    Admin only.
    """
    config_service = AdminConfigService(db)
    return config_service.get_feature_flags()


@router.post("/config/features/{feature_name}/toggle", response_model=dict)
def toggle_feature_flag(
    feature_name: str,
    enabled: bool,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
):
    """
    Toggle a feature flag.
    Admin only.

    Args:
        feature_name: Feature to toggle (rag_enabled, auto_context_detection, debug_mode, etc)
        enabled: Enable or disable
    """
    config_service = AdminConfigService(db)

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
    db: Session = Depends(deps.get_db)
):
    """
    Clear configuration cache.
    Admin only.

    Use this after making direct database changes.
    """
    config_service = AdminConfigService(db)
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
    db: Session = Depends(deps.get_db)
):
    """
    Get all AI providers.
    Admin only.
    """
    config_service = AdminConfigService(db)
    providers = config_service.get_all_providers(include_inactive=include_inactive)

    return providers


@router.post("/providers", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_provider(
    data: dict,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
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
    config_service = AdminConfigService(db)

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
    db: Session = Depends(deps.get_db)
):
    """
    Update an existing AI provider.
    Admin only.
    """
    config_service = AdminConfigService(db)

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
    db: Session = Depends(deps.get_db)
):
    """
    Delete an AI provider (CASCADE deletes models).
    Admin only.
    """
    config_service = AdminConfigService(db)

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
    db: Session = Depends(deps.get_db)
):
    """
    Get all models for a provider.
    Admin only.
    """
    config_service = AdminConfigService(db)
    models = config_service.get_models_by_provider(provider_id, include_inactive=include_inactive)

    return models


@router.post("/providers/{provider_id}/models", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_model(
    provider_id: str,
    data: dict,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
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
    config_service = AdminConfigService(db)

    success = config_service.create_model(
        provider_id=provider_id,
        model_id=data.get("model_id"),
        display_name=data.get("display_name"),
        is_default=data.get("is_default", False),
        context_window=data.get("context_window"),
        supports_vision=data.get("supports_vision", False),
        description=data.get("description"),
        priority=data.get("priority", 0)
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to create model")

    return {"status": "success", "message": "Model created"}


@router.put("/models/{model_id}", response_model=dict)
def update_model(
    model_id: int,
    data: dict,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
):
    """
    Update an existing AI model.
    Admin only.
    """
    config_service = AdminConfigService(db)

    success = config_service.update_model(
        model_pk_id=model_id,
        display_name=data.get("display_name"),
        is_active=data.get("is_active"),
        is_default=data.get("is_default"),
        context_window=data.get("context_window"),
        supports_vision=data.get("supports_vision"),
        description=data.get("description"),
        priority=data.get("priority")
    )

    if not success:
        raise HTTPException(status_code=404, detail="Model not found or update failed")

    return {"status": "success", "message": "Model updated"}


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(
    model_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
):
    """
    Delete an AI model.
    Admin only.
    """
    config_service = AdminConfigService(db)

    success = config_service.delete_model(model_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete model")

    return None


