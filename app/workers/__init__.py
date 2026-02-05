__all__ = ["IikoSyncWorker"]


def __getattr__(name: str):
    if name == "IikoSyncWorker":
        from .iiko_sync_worker import IikoSyncWorker

        return IikoSyncWorker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
