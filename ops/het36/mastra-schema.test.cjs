const test = require('node:test');
const assert = require('node:assert/strict');
const { Client } = require('pg');

test('Postiz chat storage initializes in its assigned schema without public CREATE', async (t) => {
  const { pStore } = require('/app/apps/backend/dist/libraries/nestjs-libraries/src/chat/mastra.store.js');
  t.after(() => pStore.close());
  await pStore.init();
  const client = new Client({ connectionString: process.env.DATABASE_URL });
  await client.connect();
  try {
    const { rows } = await client.query("SELECT current_schema() AS schema, has_schema_privilege(current_user,'public','CREATE') AS public_create, to_regclass('postiz.mastra_messages') IS NOT NULL AS messages");
    assert.equal(rows[0].schema, 'postiz');
    assert.equal(rows[0].public_create, false);
    assert.equal(rows[0].messages, true);
    const { rows: misplaced } = await client.query("SELECT count(*)::int AS n FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'mastra%'");
    assert.equal(misplaced[0].n, 0);
  } finally { await client.end(); }
});
