"""
In-memory session store that maps session_id → uploaded DataFrame path + metadata.
"""
from __future__ import annotations
import uuid
from typing import Dict, Any, Optional
import pandas as pd
import logging

logger = logging.getLogger(__name__)

_sessions: Dict[str, Dict[str, Any]] = {}


def create_session(df: pd.DataFrame, filename: str) -> str:
    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "df": df,
        "filename": filename,
    }
    logger.info(f"Session created: {session_id} ({filename}, {len(df)} rows)")
    return session_id


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    return _sessions.get(session_id)


def delete_session(session_id: str) -> bool:
    if session_id in _sessions:
        del _sessions[session_id]
        return True
    return False
