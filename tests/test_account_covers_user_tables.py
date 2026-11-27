import pathlib

from app.db.models import Base, User

APP = pathlib.Path(__file__).resolve().parent.parent / "app"
ACCOUNT_FILES = [APP / "api" / "account.py", *sorted((APP / "services").glob("account*.py"))]
# Tables whose rows are handled through a helper function instead of a model class name.
HELPERS = {
    "plans": ("delete_plans_for_user", "export_plans_for_user"),
    "checkins": ("delete_checkins_for_user", "export_checkins_for_user"),
}


def _account_source() -> str:
    return "\n".join(path.read_text() for path in ACCOUNT_FILES if path.exists())


def _user_owned_tables():
    """Every table with a direct foreign key to the users table."""
    users = User.__table__
    owned = []
    for table in Base.metadata.sorted_tables:
        if table is users:
            continue
        if any(fk.column.table is users for fk in table.foreign_keys):
            owned.append(table)
    return owned


def _model_name(table) -> str | None:
    for mapper in Base.registry.mappers:
        if mapper.local_table is table:
            return mapper.class_.__name__
    return None


def test_the_guard_can_see_the_plan_table():
    assert "plans" in {table.name for table in _user_owned_tables()}


def test_every_table_owned_by_a_user_is_handled_by_the_account_code():
    """New user data must be added to account export and delete, or listed here on purpose."""
    source = _account_source()
    missing = []
    for table in _user_owned_tables():
        names = HELPERS.get(table.name) or (_model_name(table) or table.name,)
        if not all(name in source for name in names):
            missing.append(table.name)
    assert not missing, f"account export/delete does not mention these user tables: {missing}"
