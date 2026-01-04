from django.apps import AppConfig


def _set_sqlite_pragmas(sender, connection, **kwargs):
    # Only applies to SQLite connections.
    if not connection.settings_dict.get("ENGINE", "").endswith("sqlite3"):
        return
    try:
        with connection.cursor() as cursor:
            # WAL allows concurrent reads while writing; busy_timeout makes SQLite wait for locks.
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA busy_timeout=5000;")
    except Exception:
        # Best-effort only.
        return


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from django.db.backends.signals import connection_created
        connection_created.connect(_set_sqlite_pragmas, dispatch_uid="core.sqlite_pragmas")
