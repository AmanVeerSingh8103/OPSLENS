import pytest

from opslens.tools import TOOLS, ToolError, execute_tool, validate_call


@pytest.mark.parametrize("name", ["exec", "run_sql", "get_revenue_summary; DROP TABLE tx", "", None, 5])
def test_unknown_tool_rejected(engine, name):
    with pytest.raises(ToolError):
        execute_tool(engine, name, {})


@pytest.mark.parametrize("args", [{"country": "x' OR '1'='1"}, {"start_month": "2010-13"}, {"sql": "SELECT * FROM tx"}, {"top_n": 9999}])
def test_bad_args_rejected(engine, args):
    with pytest.raises(ToolError):
        execute_tool(engine, "get_country_performance", args)


def test_sql_injection_via_country_is_inert(engine):
    with pytest.raises(ToolError):
        execute_tool(engine, "get_revenue_summary", {"country": "France'; DROP VIEW tx; --"})
    assert execute_tool(engine, "get_dataset_overview", {})["metrics"]["total_records"] > 0


def test_non_dict_args_rejected():
    with pytest.raises(ToolError):
        validate_call("get_dataset_overview", "SELECT 1")


def test_no_tool_accepts_free_text_code_params():
    for t in TOOLS.values():
        props = t.args_model.model_json_schema().get("properties", {})
        assert not {"sql", "query", "code", "python", "command", "column", "table"} & set(props)
        assert t.args_model.model_config.get("extra") == "forbid"


def test_row_caps(engine):
    r = execute_tool(engine, "get_product_performance", {"top_n": 25})
    assert all(len(v) <= 60 for v in r["tables"].values())
