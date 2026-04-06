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


def _normalize_column_name(col: str) -> str:
    """Normalize column name for SQL compatibility - replace spaces, parentheses, hyphens with underscores."""
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", col).strip("_")
    # Remove consecutive underscores
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.lower() if normalized else col.lower()


def build_report_tables(selected_reports: list[dict]) -> dict[str, pd.DataFrame]:
    """Build tables with normalized column names for DuckDB compatibility."""
    tables = {}
    for report in selected_reports:
        report_id = report.get("id")
        report_df = report.get("data")
        if report_id and report_df is not None:
            table_name = _normalize_table_name(report_id)
            # Create a copy with normalized column names for DuckDB
            df_normalized = report_df.copy()
            # Create mapping: normalized_name -> original_name
            column_mapping = {}
            for orig_col in df_normalized.columns:
                norm_col = _normalize_column_name(orig_col)
                column_mapping[norm_col] = orig_col
                if norm_col != orig_col:
                    df_normalized = df_normalized.rename(columns={orig_col: norm_col})
            # Store both the normalized DataFrame and the mapping
            tables[table_name] = {
                "df": df_normalized,
                "column_mapping": column_mapping,
                "original_df": report_df,  # Keep original for reference
            }
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


def _get_table_df(table_name: str, tables: dict) -> dict | None:
    """Get table info (normalized DataFrame and column mapping)."""
    return tables.get(table_name)


def _describe_table(table_info: dict, table_name: str) -> dict:
    """Describe table with normalized column names for SQL."""
    df = table_info["df"]
    column_mapping = table_info["column_mapping"]
    original_df = table_info["original_df"]
    
    # Create mapping display: normalized -> original
    column_map_display = {norm: orig for norm, orig in column_mapping.items() if norm != orig}
    
    return {
        "table_name": table_name,
        "row_count": len(df),
        "columns": list(df.columns),  # Normalized column names (use these in SQL)
        "column_mapping": column_map_display,  # Map: normalized_name -> original_name
        "original_columns": list(original_df.columns),  # Original column names for reference
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "sql_note": "Use the normalized column names shown in 'columns' field. They are SQL-safe (no spaces, parentheses, or special characters). Example: 'session_source_normalized' instead of 'Session Source (Normalized)'",
    }


def _profile_table(table_info: dict, table_name: str) -> dict:
    """Profile table with normalized column names."""
    df = table_info["df"]
    column_mapping = table_info["column_mapping"]
    original_df = table_info["original_df"]
    
    numeric_cols = list(df.select_dtypes(include="number").columns)
    dimension_cols = [col for col in df.columns if col not in numeric_cols]
    summary = {}
    if numeric_cols:
        summary = df[numeric_cols].describe().to_dict()
    
    sql_examples = [
        f"SELECT COUNT(*) AS row_count FROM {table_name}",
    ]
    if numeric_cols:
        metric = numeric_cols[0]  # Already normalized, no quoting needed
        sql_examples.append(
            f"SELECT SUM({metric}) AS total_{metric} FROM {table_name}"
        )
        # Add percentile example
        sql_examples.append(
            f"SELECT quantile_cont({metric}, 0.2) AS p20, quantile_cont({metric}, 0.5) AS p50, quantile_cont({metric}, 0.8) AS p80 FROM {table_name}"
        )
    if dimension_cols and numeric_cols:
        dim = dimension_cols[0]  # Already normalized
        metric = numeric_cols[0]
        sql_examples.append(
            f"SELECT {dim}, SUM({metric}) AS total_{metric} FROM {table_name} "
            f"GROUP BY {dim} ORDER BY total_{metric} DESC LIMIT 5"
        )
    
    # Create mapping display
    column_map_display = {norm: orig for norm, orig in column_mapping.items() if norm != orig}
    
    return {
        "table_name": table_name,
        "row_count": len(df),
        "columns": list(df.columns),  # Normalized column names (use these in SQL)
        "column_mapping": column_map_display,  # Map: normalized_name -> original_name
        "original_columns": list(original_df.columns),  # Original column names for reference
        "metric_columns": numeric_cols,
        "dimension_columns": dimension_cols,
        "numeric_summary": summary,
        "sql_examples": sql_examples,
        "sql_note": "Use the normalized column names shown in 'columns' field. They are SQL-safe (no spaces, parentheses, or special characters). No quoting needed!",
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


def run_sql_query(query: str, tables: dict) -> dict:
    allowed_tables = set(tables.keys())
    error = _validate_query(query, allowed_tables)
    if error:
        return {"error": error}

    con = duckdb.connect()
    try:
        # Register normalized DataFrames
        for name, table_info in tables.items():
            con.register(name, table_info["df"])
        try:
            result_df = con.execute(query).fetchdf()
        except Exception as exc:
            error_msg = str(exc)
            # Provide helpful guidance for common errors
            if "PERCENTILE_CONT" in query.upper() or "PERCENTILE" in query.upper():
                error_msg += " Note: DuckDB uses quantile_cont() or quantile_disc() instead of PERCENTILE_CONT. Example: SELECT quantile_cont(column, 0.2) FROM table;"
            if "syntax error" in error_msg.lower():
                if "(" in query:
                    error_msg += " Note: DuckDB may have issues with parentheses in column names. Try using double quotes instead of backticks, or use column aliases. Example: SELECT \"Column Name (Normalized)\" as col_name FROM table;"
                elif " " in query:
                    error_msg += " Note: Column names with spaces must be quoted. Use backticks: `Column Name` or double quotes: \"Column Name\""
            # Add actual column names from the table to help debug
            if "not found" in error_msg.lower() or "syntax error" in error_msg.lower():
                # Get table name from query
                table_match = re.search(rf"(?i)\bfrom\s+({ALLOWED_TABLE_PREFIX}[a-zA-Z0-9_]+)\b", query)
                if table_match:
                    table_name = table_match.group(1)
                    if table_name in tables:
                        table_info = tables[table_name]
                        df = table_info["df"]
                        error_msg += f" Available normalized columns in {table_name}: {list(df.columns)[:10]}. Use these exact names (no quoting needed)."
            return {"error": error_msg}
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
        "columns": list(result_df.columns),  # These are normalized names from the query
        "rows": result_df.to_dict(orient="records"),
        "truncated": truncated,
        "warning": warning,
    }


def explore_table_data(tool_input: dict, tables: dict) -> dict:
    if not isinstance(tool_input, dict):
        return {"error": "Invalid tool input."}

    action = tool_input.get("action")
    table_name = tool_input.get("table_name")
    query = tool_input.get("query")

    if action == "query":
        return run_sql_query(query, tables)

    if not table_name:
        return {"error": "table_name is required for this action."}

    table_info = _get_table_df(table_name, tables)
    if table_info is None:
        return {"error": f"Unknown report table: {table_name}."}

    if action == "describe":
        return _describe_table(table_info, table_name)
    if action == "profile":
        return _profile_table(table_info, table_name)

    return {"error": f"Unsupported action: {action}."}
