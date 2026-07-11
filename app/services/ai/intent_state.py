"""
Structured follow-up state (PLAN F9 Phase C).

Stores the last intent JSON per conversation so follow-ups can be resolved by
UPDATING the previous intent (short prompt) instead of re-deriving from raw
history. In-memory with TTL — chosen over a DB column because intent state is
a latency optimization only: losing it on restart silently falls back to the
original path, and the app runs single-process (see FIX_NOTES).

Flag: admin_config `intent_state_enabled` (default OFF). Effective only when
two-pass is also enabled.
"""

import time
from typing import Dict, Optional

_state: Dict[str, dict] = {}
_TTL = 3600  # 1 hour — matches a conversation session's practical lifetime
_MAX = 500


def get_intent(conversation_id: Optional[str]) -> Optional[dict]:
    if not conversation_id:
        return None
    entry = _state.get(conversation_id)
    if entry and (time.time() - entry["ts"]) < _TTL:
        return entry["intent"]
    _state.pop(conversation_id, None)
    return None


def set_intent(conversation_id: Optional[str], intent: dict) -> None:
    if not conversation_id or not isinstance(intent, dict):
        return
    if len(_state) >= _MAX:
        oldest = min(_state, key=lambda k: _state[k]["ts"])
        del _state[oldest]
    _state[conversation_id] = {"intent": intent, "ts": time.time()}


def clear() -> None:
    _state.clear()
