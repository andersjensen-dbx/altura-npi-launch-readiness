"""Run-anywhere helpers: identical notebook code works in a Databricks job and locally via
Databricks Connect (serverless) so notebooks can be committed with real execution outputs."""
import os

CATALOG = os.environ.get("NPI_CATALOG", "andersjensen_fevm_3_catalog")
SCHEMA = os.environ.get("NPI_SCHEMA", "npi_launch_readiness")
VOLUME = "landing"
LANDING = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"
PROFILE = os.environ.get("NPI_PROFILE", "fevm-andersjensen-fevm-3")
FQ = f"{CATALOG}.{SCHEMA}"


def in_databricks() -> bool:
    return "DATABRICKS_RUNTIME_VERSION" in os.environ


def get_spark():
    if in_databricks():
        from pyspark.sql import SparkSession
        return SparkSession.builder.getOrCreate()
    from databricks.connect import DatabricksSession
    return DatabricksSession.builder.profile(PROFILE).serverless().getOrCreate()


def get_ws():
    from databricks.sdk import WorkspaceClient
    return WorkspaceClient() if in_databricks() else WorkspaceClient(profile=PROFILE)


def widget(name: str, default: str) -> str:
    """Read a Databricks job/notebook parameter, falling back to env var / default locally."""
    try:
        from databricks.sdk.runtime import dbutils  # type: ignore
        return dbutils.widgets.get(name)
    except Exception:
        return os.environ.get(name.upper(), default)
