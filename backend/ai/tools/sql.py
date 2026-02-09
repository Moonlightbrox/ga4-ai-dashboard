import re

import duckdb
import pandas as pd


SOFT_ROW_LIMIT = 200                                                        # Soft limit used for warnings
HARD_ROW_LIMIT = 50                                                         # Hard cap on rows returned to the model
MAX_CELL_CHARS = 120                                                        # Truncate long text fields for cost control
ALLOWED_TABLE_PREFIX = "report_"                                            # Prefix for registered report tables


def _normalize_table_name(report_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]+", "_", report_id or "").strip("_")
    if not safe:
        safe = "unknown"
    return f"{ALLOWED_TABLE_PREFIX}{safe}"


def build_report_tables(selected_reports: list[dict]) -> dict[str, pd.DataFrame]:
    tables = {}
    for report in selected_reports:
        report_id = report.get("id")
        report_df = report.get("data")
        if report_id and report_df is not None:
            tables[_normalize_table_name(report_id)] = report_df
    return tables


def build_report_catalog(selected_reports: list[dict]) -> list[dict]:
    catalog = []
    for report in selected_reports:
        report_df = report.get("data")
        columns = []
        if report_df is not None:
            try:
                columns = list(report_df.columns)
            except AttributeError:
                columns = []
        catalog.append({
            "report_id": report.get("id"),
            "table_name": _normalize_table_name(report.get("id")),
            "report_name": report.get("name"),
            "description": report.get("description"),
            "columns": columns,
        })
    return catalog


def build_explore_tool_schema() -> dict:
    return {
        "name": "explore_table_data",
        "description": "Explore report tables with schema, profiling, or SQL query actions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["describe", "query", "profile"],
                },
                "table_name": {"type": "string"},
                "query": {"type": "string"},
                "intent": {"type": "string", "description": "Brief reason for this call."},
            },
            "required": ["action"],
        },
    }


def _get_table_df(table_name: str, tables: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    return tables.get(table_name)


def _describe_table(df: pd.DataFrame, table_name: str) -> dict:
    return {
        "table_name": table_name,
        "row_count": len(df),
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
    }


def _profile_table(df: pd.DataFrame, table_name: str) -> dict:
    numeric_cols = list(df.select_dtypes(include="number").columns)
    dimension_cols = [col for col in df.columns if col not in numeric_cols]
    summary = {}
    if numeric_cols:
        summary = df[numeric_cols].describe().to_dict()
    sql_examples = [
        f"SELECT COUNT(*) AS row_count FROM {table_name}",
    ]
    if numeric_cols:
        metric = numeric_cols[0]
        sql_examples.append(
            f"SELECT SUM({metric}) AS total_{metric} FROM {table_name}"
        )
    if dimension_cols and numeric_cols:
        dim = dimension_cols[0]
        metric = numeric_cols[0]
        sql_examples.append(
            f"SELECT {dim}, SUM({metric}) AS total_{metric} FROM {table_name} "
            f"GROUP BY {dim} ORDER BY total_{metric} DESC LIMIT 5"
        )
    return {
        "table_name": table_name,
        "row_count": len(df),
        "columns": list(df.columns),
        "metric_columns": numeric_cols,
        "dimension_columns": dimension_cols,
        "numeric_summary": summary,
        "sql_examples": sql_examples,
    }


def _validate_query(query: str, allowed_tables: set[str]) -> str | None:
    if not query or not isinstance(query, str):
        return "Query must be a non-empty string."

    query_stripped = query.strip()
    if not query_stripped.lower().startswith(("select", "with")):
        return "Only SELECT queries are allowed."

    lowered = query_stripped.lower()
    forbidden = [
        "insert", "update", "delete", "create", "drop", "alter", "attach",
        "pragma", "copy", "export", "import", "call", "transaction",
    ]
    if any(re.search(rf"\b{kw}\b", lowered) for kw in forbidden):
        return "Only read-only SELECT queries are allowed."

    if ";" in query_stripped.rstrip(";"):
        return "Only a single SQL statement is allowed."

    # Only validate report table names that appear in FROM/JOIN clauses.
    # This avoids false positives from column aliases like "report_type".
    referenced_tables = set(
        re.findall(
            rf"(?i)\b(?:from|join)\s+({ALLOWED_TABLE_PREFIX}[a-zA-Z0-9_]+)\b",
            query_stripped,
        )
    )
    if not referenced_tables:
        return "Query must reference a report table."
    unknown = referenced_tables - allowed_tables
    if unknown:
        return f"Unknown report table(s): {sorted(unknown)}."

    return None


def run_sql_query(query: str, tables: dict[str, pd.DataFrame]) -> dict:
    allowed_tables = set(tables.keys())
    error = _validate_query(query, allowed_tables)
    if error:
        return {"error": error}

    con = duckdb.connect()
    try:
        for name, df in tables.items():
            con.register(name, df)
        try:
            result_df = con.execute(query).fetchdf()
        except Exception as exc:
            return {"error": str(exc)}
    finally:
        con.close()

    if result_df is None:
        return {"error": "No results returned."}

    total_rows = len(result_df)
    truncated = False
    if total_rows > HARD_ROW_LIMIT:
        result_df = result_df.head(HARD_ROW_LIMIT)
        truncated = True

    # Truncate long text fields to reduce token usage
    for col in result_df.columns:
        if result_df[col].dtype == object:
            result_df[col] = result_df[col].astype(str).str.slice(0, MAX_CELL_CHARS)
    warning = None
    if total_rows > SOFT_ROW_LIMIT:
        warning = (
            "Large result set may increase AI costs and reduce answer quality. "
            "Consider adding filters or LIMIT to narrow the query."
        )

    return {
        "row_count": len(result_df),
        "total_rows": total_rows,
        "columns": list(result_df.columns),
        "rows": result_df.to_dict(orient="records"),
        "truncated": truncated,
        "warning": warning,
    }


def explore_table_data(tool_input: dict, tables: dict[str, pd.DataFrame]) -> dict:
    if not isinstance(tool_input, dict):
        return {"error": "Invalid tool input."}

    action = tool_input.get("action")
    table_name = tool_input.get("table_name")
    query = tool_input.get("query")

    if action == "query":
        return run_sql_query(query, tables)

    if not table_name:
        return {"error": "table_name is required for this action."}

    df = _get_table_df(table_name, tables)
    if df is None:
        return {"error": f"Unknown report table: {table_name}."}

    if action == "describe":
        return _describe_table(df, table_name)
    if action == "profile":
        return _profile_table(df, table_name)

    return {"error": f"Unsupported action: {action}."}
