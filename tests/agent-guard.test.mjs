/**
 * Direct tests for agent-guard.mjs — the file whose job is enforcing everyone else's rules.
 *
 * Until now the guard was exercised only against this repository's current tree, so an edge
 * case the tree happens not to contain (a `?` glob, a negated pattern, a rename) was simply
 * untested. These tests build throwaway git repositories with deliberately broken maps and
 * assert the guard says what the comments promise it says.
 *
 * Run: node --test tests/
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const GUARD = join(HERE, '..', 'plugins', 'executive', 'skills', 'agent-hierarchy',
  'scripts', 'agent-guard.mjs');

const { globToRegExp, parseSurfaceMap } = await import(GUARD);

/* ── globToRegExp ─────────────────────────────────────────────────────────── */

test('glob: * stays inside one segment', () => {
  const re = globToRegExp('plugins/*/SKILL.md');
  assert.ok(re.test('plugins/finance/SKILL.md'));
  assert.ok(!re.test('plugins/finance/skills/SKILL.md'));
});

test('glob: ? matches exactly one non-slash character', () => {
  const re = globToRegExp('doc?.md');
  assert.ok(re.test('doc1.md'));
  assert.ok(!re.test('doc12.md'));
  assert.ok(!re.test('doc.md'));
  assert.ok(!re.test('doc/.md'));
});

test('glob: leading **/ matches any depth including none', () => {
  const re = globToRegExp('**/SKILL.md');
  assert.ok(re.test('SKILL.md'));
  assert.ok(re.test('a/SKILL.md'));
  assert.ok(re.test('a/b/c/SKILL.md'));
});

test('glob: trailing /** matches the directory itself and everything below', () => {
  const re = globToRegExp('plugins/finance/**');
  assert.ok(re.test('plugins/finance'));
  assert.ok(re.test('plugins/finance/skills/tax/SKILL.md'));
  assert.ok(!re.test('plugins/finance-two/x'));
});

test('glob: bare ** crosses segments', () => {
  assert.ok(globToRegExp('**').test('a/b/c'));
});

test('glob: regex metacharacters in literals are escaped', () => {
  const re = globToRegExp('a.b+c/file.md');
  assert.ok(re.test('a.b+c/file.md'));
  assert.ok(!re.test('aXb+c/file.md'));
});

/* ── parseSurfaceMap ──────────────────────────────────────────────────────── */

const roster = (body) => '```roster\n' + body + '\n```\n';

test('roster: parses id, class, status, authority; omitted authority defaults', () => {
  const { roster: rows, errors } = parseSurfaceMap(roster(
    'alpha builder installed proposes\nbeta builder installed'));
  assert.equal(errors.length, 0);
  assert.deepEqual(rows.map((r) => [r.id, r.authority, r.authorityStated]), [
    ['alpha', 'proposes', true],
    ['beta', 'autonomous', false],
  ]);
});

test('roster: duplicate row, unknown class, unknown status, unknown authority, extra columns', () => {
  const { errors } = parseSurfaceMap(roster([
    'a builder installed',
    'a builder installed',
    'b wizard installed',
    'c builder shipped',
    'd builder installed sometimes',
    'e builder installed autonomous extra',
  ].join('\n')));
  assert.ok(errors.some((e) => e.includes('a listed twice')));
  assert.ok(errors.some((e) => e.includes('unknown class "wizard"')));
  assert.ok(errors.some((e) => e.includes('unknown status "shipped"')));
  assert.ok(errors.some((e) => e.includes('unknown authority "sometimes"')));
  assert.ok(errors.some((e) => e.includes('5 columns')));
});

test('surface blocks: negation is parsed and a duplicate block is an error', () => {
  const src = roster('a builder installed') +
    '```surface:a\nsrc/**\n!src/secret.txt\n```\n' +
    '```surface:a\nother/**\n```\n';
  const { owners, errors } = parseSurfaceMap(src);
  assert.equal(owners.length, 1);
  assert.deepEqual(owners[0].patterns.map((p) => [p.glob, p.negated]),
    [['src/**', false], ['src/secret.txt', true]]);
  assert.ok(errors.some((e) => e.includes('a declared twice')));
});

test('comments and blank lines in blocks are ignored', () => {
  const { roster: rows } = parseSurfaceMap(roster('# heading\n\na builder installed'));
  assert.equal(rows.length, 1);
});

/* ── check / diff, end to end in throwaway repos ─────────────────────────── */

const BASE_MAP = (extra = '') => `# map
\`\`\`roster
alpha builder installed
watch reviewer installed
${extra}\`\`\`

\`\`\`surface:alpha
**
\`\`\`
`;

function makeRepo({ map, agents = ['alpha'], decisions = null, files = {} }) {
  const dir = mkdtempSync(join(tmpdir(), 'agent-guard-test-'));
  const git = (...args) => execFileSync('git', ['-C', dir,
    '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', ...args]);
  git('init', '-q');
  writeFileSync(join(dir, 'MAP.md'), map);
  mkdirSync(join(dir, 'agents'), { recursive: true });
  for (const a of agents) writeFileSync(join(dir, 'agents', `${a}.md`), `# ${a}\n`);
  if (decisions !== null) writeFileSync(join(dir, 'DECISIONS.md'), decisions);
  for (const [path, content] of Object.entries(files)) {
    mkdirSync(join(dir, dirname(path)), { recursive: true });
    writeFileSync(join(dir, path), content);
  }
  git('add', '-A');
  git('commit', '-qm', 'fixture');
  return { dir, git };
}

function runGuard(dir, ...args) {
  const res = spawnSync('node', [GUARD, ...args], {
    cwd: dir,
    encoding: 'utf8',
    env: { ...process.env, AGENT_MAP: 'MAP.md', AGENT_DIR: 'agents', AGENT_DECISIONS: 'DECISIONS.md' },
  });
  return { code: res.status, out: res.stdout + res.stderr };
}

test('check: a coherent map passes', () => {
  const { dir } = makeRepo({ map: BASE_MAP(), agents: ['alpha', 'watch'] });
  const { code, out } = runGuard(dir, 'check');
  assert.equal(code, 0, out);
  rmSync(dir, { recursive: true, force: true });
});

test('check: an unowned path and an overlap both fail with their names', () => {
  const map = `\`\`\`roster
alpha builder installed
beta builder installed
\`\`\`
\`\`\`surface:alpha
MAP.md
agents/**
shared.txt
\`\`\`
\`\`\`surface:beta
shared.txt
\`\`\`
`;
  const { dir } = makeRepo({ map, agents: ['alpha', 'beta'], files: { 'shared.txt': 'x', 'orphan.txt': 'x' } });
  const { code, out } = runGuard(dir, 'check');
  assert.equal(code, 1);
  assert.match(out, /overlap: alpha \+ beta/);
  assert.match(out, /unowned: .*orphan\.txt/);
  rmSync(dir, { recursive: true, force: true });
});

test('check: a later negation releases a path (order is meaningful)', () => {
  const map = `\`\`\`roster
alpha builder installed
beta builder installed
\`\`\`
\`\`\`surface:alpha
**
!ceded.txt
\`\`\`
\`\`\`surface:beta
ceded.txt
\`\`\`
`;
  const { dir } = makeRepo({ map, agents: ['alpha', 'beta'], files: { 'ceded.txt': 'x' } });
  const { code, out } = runGuard(dir, 'check');
  assert.equal(code, 0, out);
  rmSync(dir, { recursive: true, force: true });
});

test('check: roster and charters must agree in both directions, planned included', () => {
  const map = `\`\`\`roster
alpha builder installed
ghost builder installed
future builder planned
\`\`\`
\`\`\`surface:alpha
**
\`\`\`
`;
  const { dir } = makeRepo({ map, agents: ['alpha', 'stray', 'future'] });
  const { code, out } = runGuard(dir, 'check');
  assert.equal(code, 1);
  assert.match(out, /ghost is marked installed but agents\/ghost\.md does not exist/);
  assert.match(out, /charter stray\.md has no roster row/);
  assert.match(out, /future is marked planned but its charter exists/);
  rmSync(dir, { recursive: true, force: true });
});

test('check: a reviewer declaring a surface fails; a gated reviewer fails', () => {
  const map = `\`\`\`roster
alpha builder installed
watch reviewer installed proposes
\`\`\`
\`\`\`surface:alpha
**
\`\`\`
\`\`\`surface:watch
somewhere/**
\`\`\`
`;
  const { dir } = makeRepo({ map, agents: ['alpha', 'watch'] });
  const { code, out } = runGuard(dir, 'check');
  assert.equal(code, 1);
  assert.match(out, /reviewer watch declares a write surface/);
  assert.match(out, /reviewer watch declares authority "proposes"/);
  rmSync(dir, { recursive: true, force: true });
});

test('check: a gated builder with no surface fails — the gate governs nothing', () => {
  const map = `\`\`\`roster
alpha builder installed
empty builder installed proposes
\`\`\`
\`\`\`surface:alpha
**
\`\`\`
`;
  const { dir } = makeRepo({ map, agents: ['alpha', 'empty'] });
  const { code, out } = runGuard(dir, 'check');
  assert.equal(code, 1);
  assert.match(out, /empty declares authority "proposes" but holds no write surface/);
  rmSync(dir, { recursive: true, force: true });
});

test('check: duplicate decision numbers fail; unique ones pass', () => {
  const dup = '## D1. one\n## D2. two\n### D2 again\n';
  const { dir } = makeRepo({ map: BASE_MAP('watch2 reviewer installed\n'), agents: ['alpha', 'watch', 'watch2'], decisions: dup });
  const { code, out } = runGuard(dir, 'check');
  assert.equal(code, 1);
  assert.match(out, /duplicate number\(s\) D2/);
  rmSync(dir, { recursive: true, force: true });
});

test('check: a pattern matching nothing is a note, not a failure', () => {
  const map = BASE_MAP().replace('```surface:alpha\n**\n```', '```surface:alpha\n**\nreserved/**\n```');
  const { dir } = makeRepo({ map, agents: ['alpha', 'watch'] });
  const { code, out } = runGuard(dir, 'check');
  assert.equal(code, 0, out);
  assert.match(out, /reserved or stale.*alpha:reserved\/\*\*/);
  rmSync(dir, { recursive: true, force: true });
});

test('diff: inside the surface passes, outside names the real owner, reviewers may change nothing', () => {
  const map = `\`\`\`roster
alpha builder installed
beta builder installed
watch reviewer installed
\`\`\`
\`\`\`surface:alpha
mine/**
MAP.md
agents/**
\`\`\`
\`\`\`surface:beta
theirs/**
\`\`\`
`;
  const { dir } = makeRepo({ map, agents: ['alpha', 'beta', 'watch'],
    files: { 'mine/a.txt': 'x', 'theirs/b.txt': 'x' } });

  writeFileSync(join(dir, 'mine', 'a.txt'), 'changed');
  let r = runGuard(dir, 'diff', 'alpha');
  assert.equal(r.code, 0, r.out);

  writeFileSync(join(dir, 'theirs', 'b.txt'), 'changed');
  r = runGuard(dir, 'diff', 'alpha');
  assert.equal(r.code, 1);
  assert.match(r.out, /belongs to beta — HANDOFF/);

  r = runGuard(dir, 'diff', 'watch');
  assert.equal(r.code, 1);
  assert.match(r.out, /this is a REVIEWER/);

  r = runGuard(dir, 'diff', 'nobody');
  assert.equal(r.code, 2);
  rmSync(dir, { recursive: true, force: true });
});

test('diff: a rename is judged by its new path', () => {
  const map = `\`\`\`roster
alpha builder installed
beta builder installed
\`\`\`
\`\`\`surface:alpha
mine/**
MAP.md
agents/**
\`\`\`
\`\`\`surface:beta
theirs/**
\`\`\`
`;
  const { dir, git } = makeRepo({ map, agents: ['alpha', 'beta'], files: { 'mine/a.txt': 'x', 'theirs/keep.txt': 'x' } });
  git('mv', 'mine/a.txt', 'theirs/moved.txt');
  const { code, out } = runGuard(dir, 'diff', 'alpha');
  assert.equal(code, 1);
  assert.match(out, /belongs to beta — HANDOFF/);
  assert.match(out, /theirs\/moved\.txt/);
  rmSync(dir, { recursive: true, force: true });
});
