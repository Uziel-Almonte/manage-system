from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text


def get_alembic_config():
    # Ajusta la ruta si tu alembic.ini no está en /app/migrations
    return Config("migrations/alembic.ini")


def test_migration_chain_has_single_head():
    """No deben existir ramas divergentes de migraciones."""
    script = ScriptDirectory.from_config(get_alembic_config())
    heads = script.get_heads()
    assert len(heads) == 1, (
        f"Se esperaba una sola head, se encontraron {len(heads)}: {heads}"
    )


def test_database_is_at_latest_migration(engine):
    """La DB de test debe estar exactamente en la última migración (head)."""
    script = ScriptDirectory.from_config(get_alembic_config())
    expected_head = script.get_current_head()

    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        assert row is not None, "No hay ninguna migración registrada en alembic_version"
        assert row[0] == expected_head, (
            f"La DB está en '{row[0]}', se esperaba la head '{expected_head}'. "
            "Corre 'flask db upgrade' contra la DB de test."
        )


def test_migration_chain_has_no_orphan_references():
    """Cada down_revision debe apuntar a una migración que realmente existe."""
    script = ScriptDirectory.from_config(get_alembic_config())
    revisions = list(script.walk_revisions())
    revision_ids = {r.revision for r in revisions}

    for rev in revisions:
        if rev.down_revision is None:
            continue
        downs = rev.down_revision if isinstance(rev.down_revision, tuple) else (rev.down_revision,)
        for d in downs:
            assert d in revision_ids, (
                f"Migración '{rev.revision}' referencia down_revision "
                f"'{d}' que no existe"
            )