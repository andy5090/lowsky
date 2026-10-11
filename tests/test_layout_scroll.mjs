import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';

const css = readFileSync(new URL('../monitor/styles.css', import.meta.url), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
const rules = selector => [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
  .filter(([, selectors]) => selectors.split(',').some(item => item.trim() === selector)).map(([, , body]) => body);
const media = query => {
  const start = css.indexOf(`@media${query}`);
  assert.notEqual(start, -1, query);
  let depth = 0, index = css.indexOf('{', start);
  const open = index;
  for (; index < css.length; index++) {
    if (css[index] === '{') depth++;
    if (css[index] === '}' && --depth === 0) break;
  }
  return css.slice(open + 1, index);
};

test('the scrolling workspace pane is the containing block for absolutely positioned descendants', () => {
  // Hidden native <select> sources and sr-only text are position:absolute. Without a positioned scroll
  // container they resolve against the page and stretch the document, so the page scrolls as well as the pane.
  assert.ok(rules('.workspace-pane').some(body => /position\s*:\s*relative/.test(body)));
});

test('the compact layout has a single scroller instead of a nested pane scroll', () => {
  const compact = media('(max-width:1099px)');
  const pane = [...compact.matchAll(/\.workspace-pane\s*\{([^}]*)\}/g)].map(match => match[1]).join(';');
  assert.doesNotMatch(pane, /overflow-y\s*:\s*(auto|scroll)/);
  assert.doesNotMatch(pane, /max-height\s*:\s*\d/);
});
