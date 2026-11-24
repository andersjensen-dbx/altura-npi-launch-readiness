import { createApp, genie, jobs, lakebase, server, serving } from '@databricks/appkit';
import { setupNpiRoutes } from './routes/npi-routes';

createApp({
  plugins: [
    genie(),
    jobs(),
    lakebase(),
    serving({ endpoints: { advisor: { env: 'DATABRICKS_SERVING_ENDPOINT_NAME' } }, timeout: 240000 }),
    server(),
  ],
  onPluginsReady(appkit) {
    setupNpiRoutes(appkit);
  },
}).catch(console.error);
