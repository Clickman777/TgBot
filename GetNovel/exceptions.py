class NovelError(Exception):
    """Base exception for novel processing errors."""
    pass

class ChapterDownloadError(NovelError):
    """Raised when a chapter fails to download or save."""
    pass

class MetadataError(NovelError):
    """Raised when novel metadata cannot be processed."""
    pass

class EpubGenerationError(NovelError):
    """Raised when the EPUB generation fails."""
    pass