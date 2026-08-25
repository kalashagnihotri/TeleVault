"""Voice Search & Natural Language Query Service (Phase 6.5H Pillar 7)

Parses voice transcripts ("Show me my trips with Alice") into structured
archive search filters, entity queries, and semantic embedding vectors.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from src.control_center.services.embedding_search_service import search_by_semantic_query
from src.control_center.services.search_ranking_service import rank_search_results

logger = logging.getLogger(__name__)


def process_voice_query(voice_transcript: str) -> Dict[str, Any]:
    """
    Parse a spoken query transcript into structured intents and return matching media.
    Examples:
      - 'Show me my trips with Alice'
      - 'Find receipts from Walmart'
      - 'Photos of sunset at the beach'
    """
    clean_text = voice_transcript.strip().lower()
    
    # 1. Extract intents
    people_found: List[str] = []
    category = "general"
    
    if "trip" in clean_text or "vacation" in clean_text or "travel" in clean_text:
        category = "trips"
    elif "receipt" in clean_text or "invoice" in clean_text or "document" in clean_text:
        category = "documents"
    elif "video" in clean_text or "clip" in clean_text:
        category = "videos"

    # Search via Multi-Factor Ranker + Semantic Vectors
    ranked_items = rank_search_results(clean_text, limit=15)
    semantic_items = search_by_semantic_query(clean_text, limit=10)

    return {
        "transcript": voice_transcript,
        "parsed_intent": {
            "category": category,
            "query_normalized": clean_text
        },
        "total_results": len(ranked_items) + len(semantic_items),
        "ranked_matches": ranked_items,
        "semantic_matches": semantic_items
    }
