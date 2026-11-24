"""Grant the Databricks App's service principal least-privilege access in Lakebase:
read-only on synced `serving` tables, read/write (no delete) on the `ops` OLTP tables."""
import sys
import psycopg
from databricks.sdk import WorkspaceClient

PROFILE, APP, EP = "fevm-andersjensen-fevm-3", "npi-control-tower", "projects/npi-readiness/branches/production/endpoints/primary"
w = WorkspaceClient(profile=PROFILE)
sp = w.apps.get(APP).service_principal_client_id
host = w.postgres.get_endpoint(name=EP).status.hosts.host
tok = w.postgres.generate_database_credential(endpoint=EP).token
with psycopg.connect(host=host, dbname="databricks_postgres", user=w.current_user.me().user_name, password=tok,
                     sslmode="require", autocommit=True) as c:
    roles = [r[0] for r in c.execute("SELECT rolname FROM pg_roles WHERE rolname = %s", (sp,)).fetchall()]
    print("app SP role present:", bool(roles))
    if not roles:
        sys.exit("SP role missing - deploy the app with the postgres resource first")
    for stmt in [
        f'GRANT USAGE ON SCHEMA serving TO "{sp}"',
        f'GRANT SELECT ON ALL TABLES IN SCHEMA serving TO "{sp}"',
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA serving GRANT SELECT ON TABLES TO "{sp}"',
        f'GRANT USAGE ON SCHEMA ops TO "{sp}"',
        f'GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA ops TO "{sp}"',
    ]:
        c.execute(stmt)
        print("ok:", stmt)
