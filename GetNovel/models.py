from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Chapter:
    """Represents a single chapter of a novel."""
    number: int
    title: str
    content: str
    url: str

@dataclass
class Novel:
    title: str
    url: str
    author: Optional[str] = None
    cover_url: Optional[str] = None
    genres: List[str] = field(default_factory=list)
    description: Optional[str] = None
    total_chapters: Optional[int] = None
    local_cover_path: Optional[str] = None
    status: Optional[str] = None
    base_chapter_url: Optional[str] = None # Added base_chapter_url field