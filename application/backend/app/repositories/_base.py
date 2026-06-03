
import logging
from typing import Type, TypeVar
from cassandra.query import SimpleStatement
from app.db import cassandra as db

logger = logging.getLogger(__name__)
T = TypeVar("T")


def execute(stmt, params=None, use_simple: bool = False):
    if use_simple:
        stmt = SimpleStatement(stmt)

    for attempt in range(2):
        try:
            session = db.session()
            return session.execute(stmt, params) if params else session.execute(stmt)
        except Exception as exc:
            if attempt == 0:
                logger.warning("Query failed, retrying after reconnect: %s", exc)
                db._session = None
                continue
            raise


def rows_to_models(rows, model_class: Type[T]) -> list[T]:
    result = []
    for row in rows:
        try:
            result.append(model_class(**dict(row._asdict())))
        except Exception as exc:
            logger.warning("Skipping malformed row for %s: %s", model_class.__name__, exc)
    return result