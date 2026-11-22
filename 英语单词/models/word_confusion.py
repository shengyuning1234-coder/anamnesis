from dataclasses import dataclass

@dataclass
class WordConfusion:
    id: int | None = None
    word_id: int = 0
    confused_with_id: int = 0
    confused_with_word: str = ''
    trigger_count: int = 0
    last_triggered_at: str = ''
    created_at: str = ''
