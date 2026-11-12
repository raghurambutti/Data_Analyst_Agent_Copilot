import pytest

from orderpilot import config
from orderpilot.safety import UnsafeSQLError, check_sql


@pytest.fixture(autouse=True)
def local_mode(monkeypatch):
    monkeypatch.setattr(config, "MODE", "local")


def test_simple_select_is_allowed_and_gets_a_limit():
    safe = check_sql("SELECT * FROM orders")
    assert safe.endswith("LIMIT 50")


def test_existing_limit_is_kept():
    assert check_sql("SELECT * FROM orders LIMIT 5") == "SELECT * FROM orders LIMIT 5"


def test_join_and_cte_are_allowed():
    sql = (
        "WITH totals AS (SELECT order_id, SUM(quantity * unit_price) AS total FROM order_items GROUP BY order_id) "
        "SELECT o.status, SUM(t.total) FROM orders o JOIN totals t ON o.order_id = t.order_id GROUP BY o.status"
    )
    check_sql(sql)  # should not raise


@pytest.mark.parametrize(
    "bad_sql",
    [
        "DELETE FROM orders",
        "DROP TABLE orders",
        "UPDATE products SET unit_price = 0",
        "INSERT INTO order_drafts VALUES ('x')",
        "SELECT * FROM orders; DROP TABLE orders",
        "SELECT * FROM secret_salaries",
        "SELECT * FROM order_drafts",  # staging table is not readable by the agent
        "",
    ],
)
def test_dangerous_sql_is_blocked(bad_sql):
    with pytest.raises(UnsafeSQLError):
        check_sql(bad_sql)


def test_extract_from_a_date_is_not_mistaken_for_a_table():
    check_sql("SELECT EXTRACT(month FROM order_date) AS m, COUNT(*) FROM orders GROUP BY m")


def test_scary_word_inside_text_is_fine():
    check_sql("SELECT * FROM products WHERE name = 'drop shipping kit'")


def test_full_unity_catalog_names_in_databricks_mode(monkeypatch):
    monkeypatch.setattr(config, "MODE", "databricks")
    check_sql("SELECT COUNT(*) FROM workspace.orderpilot.orders")
    with pytest.raises(UnsafeSQLError):
        check_sql("SELECT * FROM workspace.other_team.orders")
