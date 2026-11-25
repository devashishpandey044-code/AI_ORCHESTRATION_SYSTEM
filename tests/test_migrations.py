import pathlib

from alembic.config import Config
from alembic.script import ScriptDirectory


def _script() -> ScriptDirectory:
    config = Config("alembic.ini")
    config.set_main_option("script_location", "migrations")
    return ScriptDirectory.from_config(config)


def test_single_migration_head():
    assert len(_script().get_heads()) == 1


def test_history_is_linear_with_one_base():
    parents = [rev.down_revision for rev in _script().walk_revisions()]
    assert all(not isinstance(parent, tuple) for parent in parents)
    assert parents.count(None) == 1
    assert len(parents) == len(set(parents))  # no two migrations share a parent


def test_method_embeddings_table_is_created_once():
    files = pathlib.Path("migrations/versions").glob("*.py")
    assert sum("CREATE TABLE method_embeddings" in f.read_text() for f in files) == 1
