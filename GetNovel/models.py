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
    """Represents a novel, including its metadata and chapters."""
    title: str
    author: str
    url: str
    genres: List[str] = field(default_factory=list)
    description: Optional[str] = None
    cover_url: Optional[str] = None
    total_chapters: Optional[int] = None
    base_chapter_url: Optional[str] = None
    chapters: List[Chapter] = field(default_factory=list)
    local_cover_path: Optional[str] = None
    novel_dir: Optional[str] = None