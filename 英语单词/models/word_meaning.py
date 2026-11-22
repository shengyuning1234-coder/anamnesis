from dataclasses import dataclass

@dataclass
class WordMeaning:
    id: int | None = None
    word_id: int = 0
    meaning: str = ''
    example_sentence: str = ''
    example_translation: str = ''
    part_of_speech: str = ''
    meaning_order: int = 0
    unlocked: int = 0
    proficiency: int = 0
    review_count: int = 0
    review_stage: int = 0
    last_reviewed_at: str = ''
    next_review_at: str = ''
    created_at: str = ''
    updated_at: str = ''
