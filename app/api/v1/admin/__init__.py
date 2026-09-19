"""
NT AI Assistant - Admin API Package
====================================
Split from monolithic admin.py into domain-specific modules.
All endpoint paths remain unchanged.
"""

from fastapi import APIRouter

from ._shared import get_business_db_path as _get_business_db_path

from .analytics import router as analytics_router
from .api_keys import router as api_keys_router
from .config import router as config_router
from .contexts import router as contexts_router
from .golden_examples import router as golden_examples_router
from .hierarchy import router as hierarchy_router
from .mappings import router as mappings_router
from .onboarding import router as onboarding_router
from .providers import router as providers_router
from .query_patterns import router as query_patterns_router
from .rules import router as rules_router
from .schema import router as schema_router
from .sources import router as sources_router
from .user_data import router as user_data_router
from .vanna_docs import router as vanna_docs_router
from .warnings import router as warnings_router
from .workspaces import router as workspaces_router

router = APIRouter()
router.include_router(schema_router)
router.include_router(mappings_router)
router.include_router(rules_router)
router.include_router(golden_examples_router)
router.include_router(contexts_router)
router.include_router(onboarding_router)
router.include_router(config_router)
router.include_router(providers_router)
router.include_router(hierarchy_router)
router.include_router(warnings_router)
router.include_router(query_patterns_router)
router.include_router(analytics_router)
router.include_router(api_keys_router)
router.include_router(vanna_docs_router)
router.include_router(workspaces_router)
router.include_router(sources_router)
router.include_router(user_data_router)
