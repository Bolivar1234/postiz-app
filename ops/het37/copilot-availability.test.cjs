const { test } = require('node:test');
const assert = require('node:assert/strict');
require('reflect-metadata');
process.env.COPILOTKIT_TELEMETRY_DISABLED = 'true';
process.env.DATABASE_URL ||= 'postgresql://fixture:fixture@127.0.0.1:1/het37?schema=postiz';
const { Module } = require('@nestjs/common');
const { NestFactory } = require('@nestjs/core');
const root = '/app/apps/backend/dist';
const { CopilotController } = require(`${root}/apps/backend/src/api/routes/copilot.controller.js`);
const { SubscriptionService } = require(`${root}/libraries/nestjs-libraries/src/database/prisma/subscriptions/subscription.service.js`);
const { MastraService } = require(`${root}/libraries/nestjs-libraries/src/chat/mastra.service.js`);

for (const missing of [undefined, '', '   ']) {
  test(`unconfigured AI closes both actual HTTP handlers promptly (${JSON.stringify(missing)})`, async () => {
    if (missing === undefined) delete process.env.OPENAI_API_KEY;
    else process.env.OPENAI_API_KEY = missing;
    class FixtureModule {}
    Module({ controllers: [CopilotController], providers: [
      { provide: SubscriptionService, useValue: {} },
      { provide: MastraService, useValue: { mastra() { throw Error('unconfigured path must not initialize storage or models'); } } },
    ] })(FixtureModule);
    const app = await NestFactory.create(FixtureModule, { logger: false });
    await app.listen(0, '127.0.0.1');
    const base = `http://127.0.0.1:${app.getHttpServer().address().port}`;
    try {
      for (const route of ['/copilot/chat', '/copilot/agent']) {
        const start = performance.now();
        const response = await fetch(base + route, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ method: 'info' }), signal: AbortSignal.timeout(1000) });
        assert.equal(response.status, 503);
        assert.match(response.headers.get('content-type'), /application\/json/);
        const body = await response.json();
        assert.equal(body.code, 'AI_PROVIDER_NOT_CONFIGURED');
        assert.match(body.message, /not configured/i);
        assert.ok(performance.now() - start < 1000);
      }
    } finally {
      app.getHttpServer().closeAllConnections();
      await app.close();
    }
  });
}
