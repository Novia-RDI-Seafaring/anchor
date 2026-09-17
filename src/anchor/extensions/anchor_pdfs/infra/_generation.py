"""Pin compound store operations without exposing storage layout to callers."""
from functools import wraps


def document_view(method):
    @wraps(method)
    async def pinned(self, slug, *args, **kwargs):
        return await method(self.snapshot(slug), slug, *args, **kwargs)
    return pinned
