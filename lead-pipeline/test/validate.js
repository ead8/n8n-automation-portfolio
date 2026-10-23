#!/usr/bin/env node
/**
 * Structural validation for the lead pipeline workflows.
 *
 * For every workflows/*.json:
 *   - parses as JSON
 *   - has name / nodes / connections / settings
 *   - every node type exists in the installed n8n-nodes-base dist
 *   - every connection source and target is a real node name in the file
 *   - node names are unique
 *
 * Usage: node tests/validate.js
 */
const fs = require('fs');
const path = require('path');

const DIST = path.join(
  process.env.HOME,
  'workspace/n8n-helpdesk/n8n/node_modules/n8n-nodes-base/dist/nodes'
);
const WF_DIR = path.join(__dirname, '..', 'workflows');

function collectNodeTypes(dir, out) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) collectNodeTypes(p, out);
    else if (entry.name.endsWith('.node.json')) {
      try {
        const d = JSON.parse(fs.readFileSync(p, 'utf8'));
        if (d && d.node) out.add(d.node);
      } catch (e) { /* ignore unreadable metadata */ }
    }
  }
  return out;
}

const knownTypes = collectNodeTypes(DIST, new Set());
console.log(`Known node types in dist: ${knownTypes.size}`);

let allPass = true;
const files = fs.readdirSync(WF_DIR).filter((f) => f.endsWith('.json')).sort();

for (const file of files) {
  const problems = [];
  let wf;
  try {
    wf = JSON.parse(fs.readFileSync(path.join(WF_DIR, file), 'utf8'));
  } catch (e) {
    console.log(`FAIL ${file}: does not parse (${e.message})`);
    allPass = false;
    continue;
  }
  for (const key of ['name', 'nodes', 'connections', 'settings']) {
    if (!(key in wf)) problems.push(`missing top-level key: ${key}`);
  }
  if (!Array.isArray(wf.nodes)) {
    problems.push('nodes is not an array');
  } else {
    const names = new Set();
    for (const n of wf.nodes) {
      if (names.has(n.name)) problems.push(`duplicate node name: ${n.name}`);
      names.add(n.name);
      if (!knownTypes.has(n.type)) problems.push(`unknown node type: ${n.type} (node "${n.name}")`);
      for (const field of ['id', 'name', 'type', 'typeVersion', 'position', 'parameters']) {
        if (!(field in n)) problems.push(`node "${n.name}" missing field: ${field}`);
      }
    }
    for (const [src, byType] of Object.entries(wf.connections || {})) {
      if (!names.has(src)) problems.push(`connection source is not a node: ${src}`);
      for (const outputs of Object.values(byType)) {
        for (const group of outputs) {
          for (const target of group) {
            if (!names.has(target.node)) {
              problems.push(`connection target is not a node: ${src} -> ${target.node}`);
            }
          }
        }
      }
    }
  }
  if (problems.length) {
    allPass = false;
    console.log(`FAIL ${file} (${wf.name || 'unnamed'}):`);
    for (const p of problems) console.log(`  - ${p}`);
  } else {
    console.log(`PASS ${file} (${wf.name}, ${wf.nodes.length} nodes)`);
  }
}

console.log(allPass ? 'ALL PASS' : 'SOME FAILED');
process.exit(allPass ? 0 : 1);
