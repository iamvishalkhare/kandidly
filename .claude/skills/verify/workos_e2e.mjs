/**
 * Live e2e of the WorkOS AuthKit flow against the local compose stack.
 *  A) fresh console signup  -> own new org, lands in /console
 *  B) seeded admin (email match) -> linked, sees existing data
 *  C) candidate invite flow  -> sign-in on Start Application, auto-claim -> form
 */
import { chromium } from '/home/vishal/.npm/_npx/e41f203b7505f1fb/node_modules/playwright/index.mjs';

const WEB = 'http://localhost:5173';
const PASSWORD = process.env.E2E_PASSWORD; // staging test users share one password
const INVITE = process.env.INVITE_TOKEN;
const SHOTS = process.env.SHOTS_DIR || '/tmp';

function log(...a) { console.log(new Date().toISOString().slice(11, 19), ...a); }

async function authkitLogin(page, email) {
  // AuthKit hosted UI: email first, then password (methods vary).
  await page.waitForSelector('input[type="email"], input[name="email"]', { timeout: 30000 });
  await page.fill('input[type="email"], input[name="email"]', email);
  await page.keyboard.press('Enter');

  // Either a password input appears directly, or a method chooser first.
  try {
    await page.waitForSelector('input[type="password"]', { timeout: 8000 });
  } catch {
    const pwBtn = page.locator('button, a', { hasText: /password/i }).first();
    await pwBtn.click({ timeout: 8000 });
    await page.waitForSelector('input[type="password"]', { timeout: 15000 });
  }
  await page.fill('input[type="password"]', PASSWORD);
  await page.keyboard.press('Enter');
}

async function storedUser(page) {
  return page.evaluate(() => JSON.parse(localStorage.getItem('kandidly_user') || 'null'));
}

const browser = await chromium.launch({ headless: true });
let failures = 0;

// ── A) fresh console signup ──────────────────────────────────────────────────
try {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(`${WEB}/console`);
  await page.click('a:has-text("Sign in")');
  await authkitLogin(page, 'e2e-founder@kandidly.test');
  await page.waitForURL(`${WEB}/console`, { timeout: 45000 });
  await page.waitForTimeout(1500);
  const u = await storedUser(page);
  if (!u || u.email !== 'e2e-founder@kandidly.test' || u.role !== 'admin' || !u.org_id) {
    throw new Error(`bad stored user: ${JSON.stringify(u)}`);
  }
  log(`A OK: founder in console as admin, org_id=${u.org_id}, display_name=${u.display_name}`);
  await page.screenshot({ path: `${SHOTS}/e2e-a-founder-console.png`, fullPage: false });
  await ctx.close();
} catch (e) {
  failures++;
  log('A FAIL:', e.message);
}

// ── B) seeded admin links by email ───────────────────────────────────────────
try {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(`${WEB}/console`);
  await page.click('a:has-text("Sign in")');
  await authkitLogin(page, 'admin@kandidly.dev');
  await page.waitForURL(`${WEB}/console`, { timeout: 45000 });
  await page.waitForTimeout(2500); // let dashboard queries land
  const u = await storedUser(page);
  if (!u || u.email !== 'admin@kandidly.dev' || u.role !== 'admin') {
    throw new Error(`bad stored user: ${JSON.stringify(u)}`);
  }
  // Existing data visible: requisitions page should list seeded requisitions.
  await page.goto(`${WEB}/console/requisitions`);
  await page.waitForTimeout(2500);
  const body = await page.textContent('body');
  const seesData = /ENG-|API Test Engineer|REQ-/.test(body || '');
  if (!seesData) throw new Error('requisitions page shows no seeded data');
  log('B OK: seeded admin logged in via WorkOS, sees existing requisitions');
  await page.screenshot({ path: `${SHOTS}/e2e-b-admin-requisitions.png` });
  await ctx.close();
} catch (e) {
  failures++;
  log('B FAIL:', e.message);
}

// ── C) candidate invite flow ─────────────────────────────────────────────────
try {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(`${WEB}/i/${INVITE}`);
  await page.click('button:has-text("Start Application")');
  // Dev build shows the seeded-account picker; take the real sign-in path.
  await page.click('button:has-text("Or sign in with a real account")');
  await authkitLogin(page, 'e2e-candidate@kandidly.test');
  // Return leg: /i/<token>?autostart=1 auto-claims and routes to the form.
  await page.waitForURL(/\/apply\/[0-9a-f-]+\/form/, { timeout: 60000 });
  const u = await storedUser(page);
  if (!u || u.role !== 'candidate' || u.email !== 'e2e-candidate@kandidly.test') {
    throw new Error(`bad stored user: ${JSON.stringify(u)}`);
  }
  log(`C OK: candidate signed in + auto-claimed, now at ${page.url()}`);
  await page.screenshot({ path: `${SHOTS}/e2e-c-candidate-form.png` });
  await ctx.close();
} catch (e) {
  failures++;
  log('C FAIL:', e.message);
}

await browser.close();
if (failures) { log(`${failures} scenario(s) failed`); process.exit(1); }
log('all scenarios passed');
