
import logging
import json
import pandas as pd
import io
import asyncio
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.api import deps
from app.models.user import User
from app.models.schema_models import SchemaMetadata, SchemaSemanticMapping, SchemaBusinessRule
from app.services.ai_service import AIService
from app.services.schema_service import SchemaService

router = APIRouter()
logger = logging.getLogger(__name__)

# Pydantic Models for Analysis
class ColumnInfo(BaseModel):
    name: str
    sample_values: List[Any]
    dtype: str

class AnalysisRequest(BaseModel):
    columns: List[ColumnInfo]
    db_type: str = "generic"

class SuggestedMetadata(BaseModel):
    column_name: str
    display_name_th: str
    display_name_en: str
    description: Optional[str] = None
    data_type: str
    is_summable: bool
    is_groupable: bool
    special_notes: Optional[str] = None

class SuggestedMapping(BaseModel):
    keyword: str
    keyword_type: str
    target_column: str
    target_condition: Optional[str] = ""  # Can be empty for term/synonym types
    full_condition: Optional[str] = None  # For complex conditions
    description: Optional[str] = None

class SuggestedRule(BaseModel):
    rule_code: str
    rule_name: str
    rule_description: str
    example_correct: Optional[str] = ""
    example_wrong: Optional[str] = ""
    severity: str = "warning"

class AnalysisResult(BaseModel):
    metadata: List[SuggestedMetadata]
    mappings: List[SuggestedMapping]
    rules: List[SuggestedRule]

class ImportRequest(BaseModel):
    table_name: str
    metadata: List[SuggestedMetadata]
    mappings: List[SuggestedMapping]
    rules: List[SuggestedRule]

# --- Endpoints ---

@router.post("/analyze/upload", response_model=AnalysisRequest)
async def upload_for_analysis(
    file: UploadFile = File(...),
    current_user: User = Depends(deps.require_admin)
):
    """
    Upload a CSV or Excel file to parse columns and sample data.
    Returns: A structured object ready for AI analysis step.
    """
    try:
        content = await file.read()
        file_ext = file.filename.split('.')[-1].lower()
        
        if file_ext == 'csv':
            df = pd.read_csv(io.BytesIO(content), nrows=20) # Read only sample
        elif file_ext in ['xlsx', 'xls']:
            df = pd.read_excel(io.BytesIO(content), nrows=20)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Use CSV or Excel.")
        
        # Parse columns
        columns = []
        for col in df.columns:
            # Get non-null samples
            samples = df[col].dropna().head(5).tolist()
            # Convert numpy types to native python
            samples = [
                int(x) if isinstance(x, (int, pd.Int64Dtype)) else 
                float(x) if isinstance(x, float) else 
                str(x) 
                for x in samples
            ]
            
            columns.append(ColumnInfo(
                name=col,
                sample_values=samples,
                dtype=str(df[col].dtype)
            ))
            
        return AnalysisRequest(columns=columns, db_type="file_upload")

    except Exception as e:
        logger.error(f"Error parsing file: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")


class TextAnalysisRequest(BaseModel):
    content: str
    table_name: str

@router.post("/analyze/text", response_model=AnalysisRequest)
async def analyze_text_input(
    request: TextAnalysisRequest,
    current_user: User = Depends(deps.require_admin)
):
    """
    Parse raw CSV text input for analysis.
    """
    try:
        if not request.content.strip():
             raise HTTPException(status_code=400, detail="Empty content")

        # Use io.StringIO to treat string as file-like for pandas
        df = pd.read_csv(io.StringIO(request.content), nrows=20)
        
        columns = []
        for col in df.columns:
            samples = df[col].dropna().head(5).tolist()
            samples = [
                int(x) if isinstance(x, (int, pd.Int64Dtype)) else 
                float(x) if isinstance(x, float) else 
                str(x) 
                for x in samples
            ]
            
            columns.append(ColumnInfo(
                name=col,
                sample_values=samples,
                dtype=str(df[col].dtype)
            ))
            
        return AnalysisRequest(columns=columns, db_type="text_input")

    except Exception as e:
        logger.error(f"Error parsing text: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to parse text: {str(e)}")


@router.post("/analyze/ai-suggest", response_model=AnalysisResult)
async def get_ai_suggestions(
    request: AnalysisRequest,
    current_user: User = Depends(deps.require_admin),
    ai_service: AIService = Depends(deps.get_ai_service)
):
    """
    Send column info and samples to AI to generate metadata, mappings, and rules.
    """
    try:
        # Construct Prompt
        prompt = "Analyze the following database columns and suggest metadata, semantic mappings, and business rules.\n\n"
        prompt += "Columns:\n"
        for col in request.columns:
            prompt += f"- Name: {col.name}, Type: {col.dtype}, Samples: {col.sample_values}\n"
        
        prompt += """

        Output JSON format (all fields are required unless noted):
        {
            "metadata": [
                {
                    "column_name": "exact column name",
                    "display_name_th": "Thai display name",
                    "display_name_en": "English display name",
                    "description": "brief description",
                    "data_type": "INTEGER|TEXT|REAL|DATE",
                    "is_summable": true/false,
                    "is_groupable": true/false,
                    "special_notes": "any special notes for SQL generation"
                }
            ],
            "mappings": [
                {
                    "keyword": "the abbreviation or term users might use",
                    "keyword_type": "abbreviation" or "term" or "synonym",
                    "target_column": "which column this maps to",
                    "target_condition": "SQL condition like \"= 'value'\" or \"LIKE '%text%'\" (use empty string '' if just column reference)",
                    "description": "explanation of this mapping"
                }
            ],
            "rules": [
                {
                    "rule_code": "UNIQUE_CODE",
                    "rule_name": "Short name",
                    "rule_description": "Full description of the rule",
                    "example_correct": "SELECT ... correct SQL",
                    "example_wrong": "SELECT ... incorrect SQL",
                    "severity": "error" or "warning" or "info"
                }
            ]
        }

        Guidelines:
        1. Metadata: Suggest Thai names for all columns. Identify if numeric columns are IDs/codes (not summable) or metrics/amounts (summable).
        2. Mappings: Look for abbreviations in sample values (like "ททค.", "บดจ.", etc.) and map them to full names. IMPORTANT: target_condition must always be a string (use empty string "" if no condition).
        3. Rules: If a column usually requires specific filters or has special handling, suggest a rule.
        4. Return ONLY valid JSON, no markdown formatting.
        """

        # Call AI 
        system_prompt = "You are an expert Data Analyst and Database Administrator."
        
        # Use updated Async AI Service 
        response_text = await ai_service.provider.generate_content(prompt, system_prompt=system_prompt)
        
        # Clean JSON (remove markdown ticks if present)
        response_text = response_text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # Fallback cleanup
             response_text = response_text.replace("```", "")
             data = json.loads(response_text)

        # Post-process to handle None values from AI
        if 'mappings' in data:
            for mapping in data['mappings']:
                if mapping.get('target_condition') is None:
                    mapping['target_condition'] = ""
                if mapping.get('keyword') is None:
                     mapping['keyword'] = ""
                if mapping.get('target_column') is None:
                     mapping['target_column'] = ""

        if 'rules' in data:
            for rule in data['rules']:
                if rule.get('example_correct') is None:
                    rule['example_correct'] = ""
                if rule.get('example_wrong') is None:
                    rule['example_wrong'] = ""

        return AnalysisResult(**data)

    except Exception as e:
        logger.error(f"AI Analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"AI Analysis failed: {str(e)}")


@router.post("/analyze/import", response_model=dict)
def import_schema_suggestions(
    request: ImportRequest,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_config_db),  # the knowledge tables live in config.db (was get_db: failed since the 3-DB split)
    schema_service: SchemaService = Depends(deps.get_schema_service)
):
    """
    Import the approved suggestions into the database.

    Plan 8.1: the suggestions are an LLM's (`inferred`): they fill new rows and machine rows; a row a person or
    the contract owns keeps its content and the suggestion waits in knowledge_proposals.
    """
    from app.services.provenance import ACTIVE, INFERRED, may_replace, propose

    reason = "ข้อเสนอจาก schema analyzer — แถวที่ใช้อยู่เป็นของคน"
    queued = 0
    try:
        # 1. Import Metadata
        for meta in request.metadata:
            existing = db.query(SchemaMetadata).filter(
                SchemaMetadata.table_name == request.table_name,
                SchemaMetadata.column_name == meta.column_name
            ).first()
            
            suggested = {"display_name_th": meta.display_name_th, "display_name_en": meta.display_name_en,
                         "is_summable": meta.is_summable, "is_groupable": meta.is_groupable, "description": meta.description}
            if existing and may_replace(INFERRED, existing.source, existing.status):
                for key, value in suggested.items():
                    setattr(existing, key, value)
            elif existing:
                if any(getattr(existing, key) != value for key, value in suggested.items()):
                    queued += propose(db.connection(), "schema_metadata",
                                      {"table_name": request.table_name, "column_name": meta.column_name},
                                      suggested, INFERRED, reason=reason)
            else:
                new_meta = SchemaMetadata(
                    table_name=request.table_name,
                    column_name=meta.column_name,
                    display_name_th=meta.display_name_th,
                    display_name_en=meta.display_name_en,
                    description=meta.description,
                    data_type=meta.data_type,
                    is_summable=meta.is_summable,
                    is_groupable=meta.is_groupable,
                    special_notes=meta.special_notes,
                    source=INFERRED, status=ACTIVE,
                )
                db.add(new_meta)
        
        # 2. Import Mappings
        for mapping in request.mappings:
            existing_map = db.query(SchemaSemanticMapping).filter(
                SchemaSemanticMapping.keyword == mapping.keyword
            ).first()
            
            suggested = {"keyword_type": mapping.keyword_type, "target_column": mapping.target_column,
                         "target_condition": mapping.target_condition, "description": mapping.description}
            if existing_map and may_replace(INFERRED, existing_map.source, existing_map.status):
                for key, value in suggested.items():
                    setattr(existing_map, key, value)
            elif existing_map:
                if any(getattr(existing_map, key) != value for key, value in suggested.items()):
                    queued += propose(db.connection(), "schema_semantic_mapping", {"keyword": mapping.keyword},
                                      suggested, INFERRED, reason=reason)
            else:
                new_map = SchemaSemanticMapping(
                    keyword=mapping.keyword,
                    keyword_type=mapping.keyword_type,
                    target_column=mapping.target_column,
                    target_condition=mapping.target_condition,
                    description=mapping.description,
                    source=INFERRED, status=ACTIVE,
                )
                db.add(new_map)
                
        # 3. Import Rules
        for rule in request.rules:
            existing_rule = db.query(SchemaBusinessRule).filter(
                SchemaBusinessRule.rule_code == rule.rule_code
            ).first()
            
            suggested = {"rule_name": rule.rule_name, "rule_description": rule.rule_description,
                         "example_correct": rule.example_correct, "example_wrong": rule.example_wrong,
                         "severity": rule.severity}
            if existing_rule and may_replace(INFERRED, existing_rule.source, existing_rule.status):
                for key, value in suggested.items():
                    setattr(existing_rule, key, value)
            elif existing_rule:
                if any(getattr(existing_rule, key) != value for key, value in suggested.items()):
                    queued += propose(db.connection(), "schema_business_rules", {"rule_code": rule.rule_code},
                                      suggested, INFERRED, reason=reason)
            else:
                new_rule = SchemaBusinessRule(
                    rule_code=rule.rule_code,
                    rule_name=rule.rule_name,
                    rule_description=rule.rule_description,
                    example_correct=rule.example_correct,
                    example_wrong=rule.example_wrong,
                    severity=rule.severity,
                    source=INFERRED, status=ACTIVE,
                )
                db.add(new_rule)

        db.commit()
        schema_service.refresh_cache()
        
        return {"status": "success", "message": f"Successfully imported schema for {request.table_name}",
                "waiting_for_a_person": queued}

    except Exception as e:
        db.rollback()
        logger.error(f"Import failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
