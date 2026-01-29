"""
NT Revenue Assistant - Admin API
=================================
Admin API endpoints for schema metadata, semantic mappings, business rules,
and golden examples management.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime

from app.api import deps
from app.models.user import User
from app.models.schema_models import SchemaMetadata, SchemaSemanticMapping, SchemaBusinessRule
from app.models.feedback_models import GoldenExample
from app.schemas.admin_schemas import (
    SchemaMetadataCreate, SchemaMetadataUpdate, SchemaMetadataResponse, SchemaMetadataListResponse,
    SemanticMappingCreate, SemanticMappingUpdate, SemanticMappingResponse, SemanticMappingListResponse,
    BusinessRuleCreate, BusinessRuleUpdate, BusinessRuleResponse, BusinessRuleListResponse,
    GoldenExampleCreate, GoldenExampleUpdate, GoldenExampleResponse, GoldenExampleListResponse,
)

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
    db: Session = Depends(deps.get_db)
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
    return SchemaMetadataResponse.model_validate(column)


@router.put("/schema/columns/{column_id}", response_model=SchemaMetadataResponse)
def update_schema_column(
    column_id: int,
    data: SchemaMetadataUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
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
    return SchemaMetadataResponse.model_validate(column)


@router.delete("/schema/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schema_column(
    column_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
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
    return None


# ============================================================
# Semantic Mapping Endpoints
# ============================================================

@router.get("/mappings", response_model=SemanticMappingListResponse)
def list_semantic_mappings(
    keyword_type: Optional[str] = Query(None, description="Filter by type (abbreviation, term, synonym)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
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
    db: Session = Depends(deps.get_db)
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
    return SemanticMappingResponse.model_validate(mapping)


@router.put("/mappings/{mapping_id}", response_model=SemanticMappingResponse)
def update_semantic_mapping(
    mapping_id: int,
    data: SemanticMappingUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
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
    return SemanticMappingResponse.model_validate(mapping)


@router.delete("/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_semantic_mapping(
    mapping_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
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
    db: Session = Depends(deps.get_db)
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
    return BusinessRuleResponse.model_validate(rule)


@router.put("/rules/{rule_id}", response_model=BusinessRuleResponse)
def update_business_rule(
    rule_id: int,
    data: BusinessRuleUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
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
    return BusinessRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business_rule(
    rule_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
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
    return None


@router.post("/rules/{rule_id}/toggle", response_model=BusinessRuleResponse)
def toggle_business_rule(
    rule_id: int,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
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
    db: Session = Depends(deps.get_db)
):
    """
    Create golden example manually.
    Admin only.
    """
    example = GoldenExample(
        **data.model_dump(),
        added_by=current_user.id
    )
    db.add(example)
    db.commit()
    db.refresh(example)
    return GoldenExampleResponse.model_validate(example)


@router.put("/golden-examples/{example_id}", response_model=GoldenExampleResponse)
def update_golden_example(
    example_id: int,
    data: GoldenExampleUpdate,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db)
):
    """
    Update golden example.
    Admin only.
    """
    example = db.query(GoldenExample).filter(GoldenExample.id == example_id).first()
    if not example:
        raise HTTPException(status_code=404, detail="Golden example not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(example, key, value)

    db.commit()
    db.refresh(example)
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
    """
    example = db.query(GoldenExample).filter(GoldenExample.id == example_id).first()
    if not example:
        raise HTTPException(status_code=404, detail="Golden example not found")

    db.delete(example)
    db.commit()
    return None


# ============================================================
# Refresh Cache Endpoint
# ============================================================

    return {
        "status": "success",
        "message": "Schema cache refresh triggered. Changes will take effect on next query."
    }

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
