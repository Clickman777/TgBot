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
    cover_url: Optional[str] = None
    total_chapters: Optional[int] = None
    base_chapter_url: Optional[str] = None
    chapters: List[Chapter] = field(default_factory=list)
    # Local path to the downloaded cover image
    local_cover_path: Optional[str] = None
    # Local directory where novel files are stored
    novel_dir: Optional[str] = None