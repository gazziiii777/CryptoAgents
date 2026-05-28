import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from db.research import models  # noqa: F401 — registers tables on ResearchBase.metadata
from db.research.base import ResearchBase

_MYSQL = mysql.dialect()


@pytest.mark.unit
@pytest.mark.parametrize("table", list(ResearchBase.metadata.tables.values()))
def test_research_table_compiles_on_mariadb(table) -> None:
    """create_all research-моделей должен компилироваться под MariaDB.

    Ловит unlengthed VARCHAR (MariaDB требует длину) без живой БД — юнит-тесты на
    SQLite это пропускают, поэтому проверяем DDL прямо против mysql-диалекта.
    """
    CreateTable(table).compile(dialect=_MYSQL)
