const assert = require('node:assert/strict');
const { test, before, after } = require('node:test');
const { randomUUID } = require('node:crypto');
const root = '/app/apps/backend/dist';
const { PrismaService } = require(`${root}/libraries/nestjs-libraries/src/database/prisma/prisma.service.js`);
const { OrganizationRepository } = require(`${root}/libraries/nestjs-libraries/src/database/prisma/organizations/organization.repository.js`);
const { OrganizationService } = require(`${root}/libraries/nestjs-libraries/src/database/prisma/organizations/organization.service.js`);
const { AuthService } = require(`${root}/apps/backend/src/services/auth/auth.service.js`);
const { AuthController } = require(`${root}/apps/backend/src/api/routes/auth.controller.js`);
const { UsersController } = require(`${root}/apps/backend/src/api/routes/users.controller.js`);
const { AuthMiddleware } = require(`${root}/apps/backend/src/services/auth/auth.middleware.js`);
const { EmailService } = require(`${root}/libraries/nestjs-libraries/src/services/email.service.js`);
const { NotificationService } = require(`${root}/libraries/nestjs-libraries/src/database/prisma/notifications/notification.service.js`);
const { CreateOrgUserDto } = require(`${root}/libraries/nestjs-libraries/src/dtos/auth/create.org.user.dto.js`);
const { AuthService: Tokens } = require(`${root}/libraries/helpers/src/auth/auth.service.js`);
const { parseTeamInvitation } = require(`${root}/libraries/helpers/src/auth/team-invitation.js`);

const db = new PrismaService();
const repo = new OrganizationRepository({ model: db }, { model: db }, { model: db }, db);
const mail = [];
let provider = true;
const notifications = { hasEmailProvider: () => provider, sendEmail: async (...args) => mail.push(args) };
const email = { hasProvider: () => provider, ensureConfigured: () => { if (!provider) throw Error('Email delivery is not configured'); }, sendEmailSync: async (...args) => mail.push(args) };
const orgs = new OrganizationService(repo, notifications);
const users = {
  getUserByEmail: (email) => db.user.findFirst({ where: { email, providerName: 'LOCAL', deletedAt: null } }),
  getUserById: (id) => db.user.findUnique({ where: { id } }),
  activateUser: (id) => db.user.update({ where: { id }, data: { activated: true } }),
};
const auth = new AuthService(users, orgs, email, {});
const controller = new AuthController(auth, email);
const userController = new UsersController(null, null, auth, orgs, users, null);
const response = () => ({ code: 200, body: null, cookies: [], headers: {},
  status(code) { this.code = code; return this; }, json(body) { this.body = body; return this; },
  send(body) { this.body = body; return this; }, header(k, v) { this.headers[k] = v; return this; },
  cookie(k, v) { this.cookies.push(k); return this; },
});
let a, b;
const owner = { email: 'owner@example.invalid', name: 'Fixture owner' };
async function invite(email, role = 'USER', org = a) {
  const result = await orgs.inviteTeamMember(org, owner, { email, role, sendEmail: false });
  const token = new URL(result.url).searchParams.get('org');
  const claims = auth.getOrgFromCookie(token);
  assert.ok(claims);
  return { token, claims };
}
async function register(email, token, route = controller) {
  const res = response();
  const dto = Object.assign(new CreateOrgUserDto(), { provider: 'LOCAL', password: 'fixture-password-123', email, company: 'Ignored fixture company' });
  await route.register({ cookies: token ? { org: token } : {} }, dto, res, '127.0.0.1', 'HET34 fixture');
  return res;
}
before(async () => {
  assert.match(process.env.DATABASE_URL, /het34_invites/);
  process.env.DISABLE_REGISTRATION = 'true';
  await db.$connect();
  await db.userOrganization.deleteMany(); await db.teamInvitation.deleteMany();
  await db.subscription.deleteMany(); await db.user.deleteMany(); await db.organization.deleteMany();
  a = await db.organization.create({ data: { name: 'Fixture team A' } });
  b = await db.organization.create({ data: { name: 'Fixture team B' } });
});
after(async () => { await db.$disconnect(); });

test('ordinary signup remains closed and creates no identity', async () => {
  const res = await register('uninvited@example.invalid');
  assert.equal(res.code, 400); assert.match(res.body, /Registration is disabled/);
  assert.equal(await db.user.count({ where: { email: 'uninvited@example.invalid' } }), 0);
});
test('valid invite permits normalized recipient, preserves team/role, requires email activation, creates no extra team', async () => {
  const issued = await invite('  Member@Example.Invalid  ');
  const gate = await controller.canRegister({ cookies: { org: issued.token } });
  assert.equal(gate.register, true);
  const count = await db.organization.count();
  const res = await register('MEMBER@example.invalid', issued.token);
  assert.equal(res.code, 200); assert.deepEqual(res.body, { activate: true }); assert.deepEqual(res.cookies, []);
  assert.equal(await db.organization.count(), count);
  const user = await users.getUserByEmail('member@example.invalid'); assert.equal(user.activated, false);
  const membership = await db.userOrganization.findUnique({ where: { userId_organizationId: { userId: user.id, organizationId: a.id } } });
  assert.equal(membership.role, 'USER');
  assert.equal(await db.userOrganization.count({ where: { userId: user.id, organizationId: b.id } }), 0);
  assert.equal((await db.teamInvitation.findUnique({ where: { id: issued.claims.id } })).consumedBy, user.id);
  const middleware = new AuthMiddleware(orgs, users);
  await assert.rejects(() => middleware.use({ headers: {}, cookies: { auth: Tokens.signJWT(user) } }, {}, () => { throw Error('unactivated identity reached next'); }));
  assert.equal(mail.some(args => args[0] === user.email && args[1] === 'Activate your account'), true);
});
test('wrong recipient cannot register or consume another invitation', async () => {
  const issued = await invite('intended@example.invalid', 'ADMIN');
  const res = await register('other@example.invalid', issued.token);
  assert.equal(res.code, 400); assert.match(res.body, /recipient/);
  assert.equal(await db.user.count({ where: { email: 'other@example.invalid' } }), 0);
  assert.equal((await db.teamInvitation.findUnique({ where: { id: issued.claims.id } })).consumedAt, null);
});
test('tampered, expired, missing-purpose, and unissued signed claims cannot admit users', async () => {
  const issued = await invite('expired@example.invalid');
  for (const token of [issued.token.slice(0, -2) + 'xx', Tokens.signJWT({ ...issued.claims, timeLimit: new Date(0).toISOString() }), Tokens.signJWT({ ...issued.claims, purpose: 'login' }), Tokens.signJWT({ ...issued.claims, id: randomUUID() })]) {
    const res = await register('expired@example.invalid', token);
    assert.equal(res.code, 400);
  }
  assert.equal(parseTeamInvitation({ ...issued.claims, role: 'SUPERADMIN' }), false);
  assert.equal(await db.user.count({ where: { email: 'expired@example.invalid' } }), 0);
});
test('join-org enforces signed recipient and persisted organization/role, including cross-team negative', async () => {
  const user = await db.user.create({ data: { email: 'existing@example.invalid', providerName: 'LOCAL', timezone: 0, activated: true } });
  const wrong = await invite('somebodyelse@example.invalid');
  await assert.rejects(() => userController.joinOrg(user, wrong.token, response()), /recipient/);
  const issued = await invite(user.email, 'ADMIN');
  for (const claims of [{ ...issued.claims, orgId: b.id }, { ...issued.claims, role: 'USER' }]) {
    await assert.rejects(() => userController.joinOrg(user, Tokens.signJWT(claims), response()), /expired or already used/);
  }
  const res = response(); await userController.joinOrg(user, issued.token, res);
  assert.equal(res.body.id, a.id);
  assert.equal((await db.userOrganization.findUnique({ where: { userId_organizationId: { userId: user.id, organizationId: a.id } } })).role, 'ADMIN');
  assert.equal(await db.userOrganization.count({ where: { userId: user.id, organizationId: b.id } }), 0);
  await assert.rejects(() => userController.joinOrg(user, issued.token, response()), /expired or already used/);
});
test('concurrent replay commits one membership and one consumption', async () => {
  const user = await db.user.create({ data: { email: 'concurrent@example.invalid', providerName: 'LOCAL', timezone: 0, activated: true } });
  const issued = await invite(user.email);
  const results = await Promise.allSettled([orgs.addUserToOrg(user.id, issued.claims), orgs.addUserToOrg(user.id, issued.claims)]);
  assert.equal(results.filter(x => x.status === 'fulfilled').length, 1);
  assert.equal(await db.userOrganization.count({ where: { userId: user.id, organizationId: a.id } }), 1);
});
test('membership failure rolls back consumption; absent mail does not create activated invitee', async () => {
  const user = await db.user.create({ data: { email: 'rollback@example.invalid', providerName: 'LOCAL', timezone: 0, activated: true } });
  await db.userOrganization.create({ data: { userId: user.id, organizationId: a.id, role: 'USER' } });
  const issued = await invite(user.email);
  await assert.rejects(() => orgs.addUserToOrg(user.id, issued.claims));
  assert.equal((await db.teamInvitation.findUnique({ where: { id: issued.claims.id } })).consumedAt, null);
  const pending = await invite('no-mail@example.invalid'); provider = false;
  const res = await register('no-mail@example.invalid', pending.token);
  assert.equal(res.code, 400); assert.match(res.body, /Email delivery/);
  assert.equal(await db.user.count({ where: { email: 'no-mail@example.invalid' } }), 0);
  provider = true;
});

test('concurrent invited signup creates one inactive identity in the invited team only', async () => {
  const issued = await invite('new-race@example.invalid');
  const count = await db.organization.count();
  const responses = await Promise.all([register('new-race@example.invalid', issued.token), register('new-race@example.invalid', issued.token)]);
  assert.deepEqual(responses.map(x => x.code).sort(), [200, 400]);
  assert.equal(await db.user.count({ where: { email: 'new-race@example.invalid' } }), 1);
  assert.equal(await db.organization.count(), count);
  const user = await users.getUserByEmail('new-race@example.invalid');
  assert.equal(user.activated, false);
  assert.equal(await db.userOrganization.count({ where: { userId: user.id, organizationId: a.id } }), 1);
});
test('actual EmailService rejects missing sender before consumption and reports provider failure with recoverable activation resend', async () => {
  const actualEmail = new EmailService(null);
  let attempts = 0; let failing = true; let activationHtml;
  actualEmail.emailService = { name: 'isolated-fixture', validateEnvKeys: [], async sendEmail(_to, _subject, html) {
    attempts++;
    if (failing) throw Error('isolated simulated transport failure');
    activationHtml = html; return { id: 'isolated-fixture-delivery' };
  } };
  const actualAuth = new AuthService(users, orgs, actualEmail, {});
  const actualController = new AuthController(actualAuth, actualEmail);
  const issued = await invite('delivery-retry@example.invalid');
  delete process.env.EMAIL_FROM_ADDRESS; delete process.env.EMAIL_FROM_NAME;
  const missing = await register('delivery-retry@example.invalid', issued.token, actualController);
  assert.equal(missing.code, 400); assert.match(missing.body, /not fully configured/);
  assert.equal(await db.user.count({ where: { email: 'delivery-retry@example.invalid' } }), 0);
  assert.equal((await db.teamInvitation.findUnique({ where: { id: issued.claims.id } })).consumedAt, null);
  process.env.EMAIL_FROM_ADDRESS = 'fixture@example.invalid'; process.env.EMAIL_FROM_NAME = 'Isolated test';
  const failed = await register('delivery-retry@example.invalid', issued.token, actualController);
  assert.equal(failed.code, 400); assert.match(failed.body, /Activation email delivery failed/);
  assert.equal(attempts, 3);
  const user = await users.getUserByEmail('delivery-retry@example.invalid'); assert.equal(user.activated, false);
  assert.equal((await db.teamInvitation.findUnique({ where: { id: issued.claims.id } })).consumedBy, user.id);
  failing = false;
  await actualAuth.resendActivationEmail(user.email);
  assert.equal(attempts, 4); assert.match(activationHtml, /auth\/activate\//);
  const code = activationHtml.match(/auth\/activate\/([^"<]+)/)[1];
  const activatedToken = await actualAuth.activate(code, '');
  assert.ok(activatedToken); assert.equal((await users.getUserById(user.id)).activated, true);
});
test('paid STANDARD team restriction still rejects invitation consumption', async () => {
  const user = await db.user.create({ data: { email: 'standard@example.invalid', providerName: 'LOCAL', timezone: 0, activated: true } });
  const issued = await invite(user.email);
  await db.subscription.create({ data: { organizationId: a.id, subscriptionTier: 'STANDARD', period: 'MONTHLY', totalChannels: 1 } });
  process.env.STRIPE_PUBLISHABLE_KEY = 'fixture-only';
  await assert.rejects(() => orgs.addUserToOrg(user.id, issued.claims), /plan does not include/);
  assert.equal((await db.teamInvitation.findUnique({ where: { id: issued.claims.id } })).consumedAt, null);
  delete process.env.STRIPE_PUBLISHABLE_KEY;
  await db.subscription.deleteMany({ where: { organizationId: a.id } });
});
test('real Nest HTTP DTO/cookie boundary keeps signup closed and admits only valid invited email', async () => {
  const { Module, ValidationPipe } = require('@nestjs/common');
  const { NestFactory } = require('@nestjs/core');
  const cookieParser = require('cookie-parser');
  class FixtureModule {}
  const { ThrottlerModule } = require('@nestjs/throttler');
  Module({ imports: [ThrottlerModule.forRoot([{ name: 'default', ttl: 60000, limit: 1000 }])], controllers: [AuthController], providers: [{ provide: AuthService, useValue: auth }, { provide: EmailService, useValue: email }] })(FixtureModule);
  const app = await NestFactory.create(FixtureModule, { logger: false });
  app.use(cookieParser()); app.useGlobalPipes(new ValidationPipe({ transform: true }));
  await app.listen(0, '127.0.0.1');
  const base = await app.getUrl();
  try {
    const issued = await invite('http-fixture@example.invalid');
    const body = { email: 'http-fixture@example.invalid', password: 'fixture-password-123', provider: 'LOCAL', company: 'Isolated HTTP fixture' };
    const { spawn } = require('node:child_process');
    const frontend = spawn(process.execPath, ['/app/node_modules/next/dist/bin/next', 'start', '-p', '4201'], {
      cwd: '/app/apps/frontend', env: { ...process.env, BACKEND_INTERNAL_URL: base }, stdio: 'ignore',
    });
    try {
      let ready = false;
      for (let i = 0; i < 100; i++) {
        try { const probe = await fetch('http://127.0.0.1:4201/auth/login'); if (probe.status === 200) { ready = true; break; } } catch {}
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      assert.equal(ready, true);
      let page = await fetch('http://127.0.0.1:4201/auth');
      assert.match(await page.text(), /Registration is disabled/);
      page = await fetch('http://127.0.0.1:4201/auth', { headers: { Cookie: 'org=' + issued.token } });
      const html = await page.text();
      assert.equal(page.status, 200); assert.doesNotMatch(html, /Registration is disabled/);
      assert.match(html, /name="email"/);
      assert.match(html, /https:\/\/socials\.qwntik\.com\/api/);
    } finally {
      if (frontend.exitCode === null) {
        frontend.kill('SIGTERM');
        await Promise.race([new Promise(resolve => frontend.once('exit', resolve)), new Promise(resolve => setTimeout(resolve, 3000))]);
        if (frontend.exitCode === null) frontend.kill('SIGKILL');
      }
    }

    let r = await fetch(base + '/auth/register', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    assert.equal(r.status, 400);
    r = await fetch(base + '/auth/can-register', { headers: { Cookie: 'org=' + issued.token } });
    assert.equal((await r.json()).register, true);
    r = await fetch(base + '/auth/register', { method: 'POST', headers: { 'content-type': 'application/json', Cookie: 'org=' + issued.token }, body: JSON.stringify({ ...body, email: 'wrong-http@example.invalid' }) });
    assert.equal(r.status, 400);
    r = await fetch(base + '/auth/register', { method: 'POST', headers: { 'content-type': 'application/json', Cookie: 'org=' + issued.token }, body: JSON.stringify({ ...body, email: 'not-an-email' }) });
    assert.equal(r.status, 400);
    r = await fetch(base + '/auth/register', { method: 'POST', headers: { 'content-type': 'application/json', Cookie: 'org=' + issued.token }, body: JSON.stringify(body) });
    assert.equal(r.status, 200); assert.deepEqual(await r.json(), { activate: true });
    assert.equal(r.headers.get('set-cookie'), null);
  } finally { await app.close(); }
});


test('invitation send waits for actual EmailService outcome and never reports failed delivery as sent', async () => {
  const actualEmail = new EmailService(null);
  let accepted = false;
  actualEmail.emailService = { name: 'isolated-invite-fixture', validateEnvKeys: [], async sendEmail() {
    if (!accepted) throw Error('isolated invite transport failure');
    return { id: 'isolated-invite-provider-accepted' };
  } };
  const actualNotifications = new NotificationService(null, actualEmail, repo, null);
  const actualOrgs = new OrganizationService(repo, actualNotifications);
  process.env.EMAIL_FROM_ADDRESS = 'fixture@example.invalid'; process.env.EMAIL_FROM_NAME = 'Isolated test';
  await assert.rejects(() => actualOrgs.inviteTeamMember(a, owner, { email: 'invite-send@example.invalid', role: 'USER', sendEmail: true }), /email delivery failed/);
  accepted = true;
  const result = await actualOrgs.inviteTeamMember(a, owner, { email: 'invite-send@example.invalid', role: 'USER', sendEmail: true });
  assert.ok(result.url); assert.equal(await db.user.count({ where: { email: 'invite-send@example.invalid' } }), 0);
});
