from sqlalchemy import text, inspect
from config.database import engine
from utils.logger import setup_logger
import uuid

logger = setup_logger(__name__)

correlation_id = str(uuid.uuid4())


def table_exists(table_name: str) -> bool:
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    if not table_exists(table_name):
        return False
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def add_onboarding_choices_column():
    table_name = "user"
    column_name = "onboarding_choices"

    if not table_exists(table_name):
        logger.warning(
            "User table does not exist yet",
            extra={"correlation_id": correlation_id, "table": table_name}
        )
        return

    if column_exists(table_name, column_name):
        logger.info(
            "Column 'onboarding_choices' already exists in user table",
            extra={"correlation_id": correlation_id, "table": table_name, "column": column_name}
        )
        return

    with engine.begin() as conn:
        conn.execute(text(
            f'ALTER TABLE "{table_name}" ADD COLUMN {column_name} JSON DEFAULT \'[]\''
        ))

    logger.info(
        "Added 'onboarding_choices' column to user table",
        extra={"correlation_id": correlation_id, "table": table_name, "column": column_name}
    )


def run():
    add_onboarding_choices_column()
