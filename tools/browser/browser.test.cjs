const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs/promises');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { test } = require('node:test');
const { chromium, firefox } = require('playwright');

const root = path.resolve(__dirname, '../..');

async function multiline(page, selector) {
  const state = await page.locator(selector).first().evaluate(element => ({
    text: element.textContent, visible: element.innerText,
    whitespace: getComputedStyle(element).whiteSpace
  }));
  assert.equal(state.whitespace, 'pre-wrap');
  assert.equal(state.visible, state.text);
  assert.ok(state.text.includes('\n'));
}

async function download(page, selector) {
  const pending = page.waitForEvent('download');
  await page.locator(selector).press('Enter');
  const result = await pending;
  assert.equal(await result.failure(), null);
  const stream = await result.createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf8');
}

for (const [name, engine] of Object.entries({ chromium, firefox })) {
  test(`${name}: offline studio edits, exports and print rendering`, { timeout: 90000 }, async () => {
    const output = path.join(root, 'private-output');
    await fs.mkdir(output, { recursive: true, mode: 0o700 });
    const directory = await fs.mkdtemp(path.join(output, 'browser-'));
    let browser;
    try {
      const documents = JSON.parse(execFileSync('python3', [path.join(__dirname, 'generate_fixtures.py')],
        { cwd: root, timeout: 15000, encoding: 'utf8', stdio: 'pipe' }));
      for (const filename of ['fixture.json', 'studio.html', 'plan.html', 'cards.html']) {
        await fs.writeFile(path.join(directory, filename), documents[filename], { flag: 'wx', mode: 0o600 });
      }
      const fixture = JSON.parse(await fs.readFile(path.join(directory, 'fixture.json'), 'utf8'));
      browser = await engine.launch({ headless: true });
      const context = await browser.newContext({ offline: true, acceptDownloads: true,
        serviceWorkers: 'block', viewport: { width: 1280, height: 900 } });
      context.setDefaultTimeout(10000);
      const external = [], errors = [];
      context.on('request', request => {
        if (/^(?:https?|wss?):/.test(request.url())) external.push(request.url());
      });
      await context.route(/^(?:https?):/, route => route.abort());
      await context.routeWebSocket(/.*/, socket => {
        external.push(socket.url()); socket.close();
      });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      page.on('dialog', dialog => dialog.dismiss());
      const open = file => page.goto(pathToFileURL(path.join(directory, file)).href);
      const snapshot = async () => JSON.parse(await page.locator('#draft-json').inputValue());
      const dirty = () => page.locator('#draft-status').getAttribute('data-dirty');

      await open('studio.html');
      assert.equal(await page.locator('#export-json').isDisabled(), true);
      await page.keyboard.press('Tab');
      assert.equal(await page.locator('.skip-link').evaluate(element => element === document.activeElement), true);
      await page.keyboard.press('Enter');
      await page.locator('[data-section-toggle="basics"]').press('Enter');
      assert.equal(await page.locator('#field-title').isVisible(), false);
      await page.locator('#first-issue').press('Enter');
      assert.equal(await page.locator('#field-title').evaluate(element => element === document.activeElement), true);
      assert.equal(await page.locator('#field-title').isVisible(), true);

      await page.locator('#import-json').setInputFiles(path.join(directory, 'fixture.json'));
      await page.waitForFunction(() => document.querySelector('#operation-status').textContent.startsWith('JSON imported locally.'));
      assert.deepEqual(await snapshot(), fixture);
      assert.equal(await dirty(), 'false');
      await page.locator('#field-notes').press('ControlOrMeta+End');
      await page.keyboard.press('Enter');
      await page.keyboard.type('Keyboard edit retained');
      const edited = await snapshot();
      assert.equal(edited.notes, fixture.notes + '\nKeyboard edit retained');
      assert.equal(await dirty(), 'true');
      assert.equal(await page.locator('#confirm-saved').isDisabled(), true);

      // A filtered, compact preview must not trim exported data.
      await page.locator('#preview-section').selectOption('4');
      await page.locator('#compact-preview').check();
      await page.locator('#large-preview').check();
      assert.deepEqual(await snapshot(), edited);
      assert.deepEqual(JSON.parse(await download(page, '#export-json')), edited);
      assert.equal(await dirty(), 'true');
      assert.equal(await page.locator('#confirm-saved').isEnabled(), true);
      await page.locator('#confirm-saved').press('Enter');
      assert.equal(await dirty(), 'false');
      await page.locator('#field-title').press('End');
      await page.keyboard.type(' edited');
      const finalPlan = await snapshot();
      assert.equal(await dirty(), 'true');
      assert.equal(await page.locator('#confirm-saved').isDisabled(), true);
      const full = await download(page, '#export-html');
      const cards = await download(page, '#export-cards');
      for (const html of [full, cards]) {
        assert.ok(html.includes('Fictional contact\nSecond name line'));
        assert.ok(html.includes('Fictional first line\nFictional second line\tTabbed detail'));
        assert.equal(/<script|<img/i.test(html), false);
      }
      assert.ok(full.includes('&lt;img'));
      assert.ok(full.includes('Keyboard edit retained'));
      assert.equal(await dirty(), 'true');
      await fs.writeFile(path.join(directory, 'export-plan.html'), full, { mode: 0o600 });
      await fs.writeFile(path.join(directory, 'export-cards.html'), cards, { mode: 0o600 });

      // Invalid replacement and cancelled reset both retain unsaved edits.
      await page.locator('#import-json').setInputFiles({ name: 'invalid.json',
        mimeType: 'application/json', buffer: Buffer.from('{"schema_version": 1}') });
      await page.waitForFunction(() => document.querySelector('#operation-status').textContent.startsWith('Import failed.'));
      assert.deepEqual(await snapshot(), finalPlan);
      await page.locator('#reset').press('Enter');
      assert.deepEqual(await snapshot(), finalPlan);
      await page.locator('#preview-section').selectOption('all');
      await page.locator('#json-inspector summary').press('Enter');
      assert.equal(await page.locator('#draft-json').isVisible(), true);
      await page.emulateMedia({ media: 'print' });
      for (const selector of ['#editor-column', '#preview-section', '#compact-preview', '#large-preview', '#json-inspector']) {
        assert.equal(await page.locator(selector).isVisible(), false);
      }
      assert.equal(await page.locator('#preview-content').isVisible(), true);
      assert.equal(await page.locator('#preview-content h4').count(), 5);
      await multiline(page, '#preview-content h3');
      await page.emulateMedia({ media: 'screen' });
      await page.setViewportSize({ width: 360, height: 800 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      assert.deepEqual(await page.evaluate(() => [localStorage.length, sessionStorage.length]), [0, 0]);
      await page.close({ runBeforeUnload: false });

      const rendered = await context.newPage();
      rendered.on('pageerror', error => errors.push(error.message));
      for (const media of ['screen', 'print']) {
        await rendered.emulateMedia({ media });
        for (const [file, selectors] of [
          ['plan.html', ['#plan-title', '#contacts h3']],
          ['cards.html', ['article h2', 'article footer']],
          ['export-plan.html', ['h1', 'article h3']],
          ['export-cards.html', ['h1', 'article h3']]
        ]) {
          await rendered.goto(pathToFileURL(path.join(directory, file)).href);
          for (const selector of selectors) await multiline(rendered, selector);
          assert.equal(await rendered.locator('script, img, iframe, link[href], source').count(), 0);
          assert.equal(await rendered.locator('html').getAttribute('lang'), 'en');
        }
      }
      assert.deepEqual(external, [], 'No external page requests are permitted');
      assert.deepEqual(errors, [], 'Generated pages must not raise JavaScript errors');
      await context.close();
    } finally {
      if (browser) await browser.close();
      await fs.rm(directory, { recursive: true, force: true });
    }
  });
}
