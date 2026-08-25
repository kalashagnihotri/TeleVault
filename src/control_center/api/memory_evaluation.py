"""Memory Quality Evaluation & Ranked Search API Router (Phase 6.5G)"""

from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter
from pydantic import BaseModel

from src.control_center.services.memory_evaluation_service import evaluate_memory_quality
from src.control_center.services.search_ranking_service import rank_search_results

router = APIRouter(prefix="/api", tags=["Memory Evaluation & Search"])


@router.get("/memories/quality_evaluation")
def get_memory_quality() -> Dict[str, Any]:
    return evaluate_memory_quality()


@router.get("/archive/ranked_search")
def get_ranked_search(q: str, limit: int = 20) -> List[Dict[str, Any]]:
    return rank_search_results(query=q, limit=limit)
