// Exercise the real page's view functions without a browser or third-party DOM.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

class Element {
  constructor(tag, text = '') { this.tag = tag; this.children = []; this.attrs = {}; this.events = {}; this.dataset = {}; this.nodeType = 1; this.text = text; this.style = {}; this.classList = {toggle(){},add(){},remove(){}}; }
  setAttribute(key, value) { this.attrs[key] = value; if (key.startsWith('data-')) this.dataset[key.slice(5)] = value; }
  append(...items) { this.children.push(...items); }
  prepend(...items) { this.children.unshift(...items); }
  replaceChildren(...items) { this.children = items; }
  addEventListener(key, fn) { this.events[key] = fn; }
  querySelectorAll(selector) { return this.children.flatMap(child => typeof child === 'object' ? [...(selector === '[data-item]' && child.attrs?.['data-item'] ? [child] : []), ...child.querySelectorAll(selector)] : []); }
  get textContent() { return this.text + this.children.map(child => typeof child === 'object' ? child.textContent : child).join(' '); }
  set textContent(value) { this.text = value; this.children = []; }
  all(tag) { return [...(this.tag === tag ? [this] : []), ...this.children.flatMap(child => typeof child === 'object' ? child.all(tag) : [])]; }
}
const controls = new Map();
const document = {
  createElement: tag => new Element(tag),
  createElementNS: (_, tag) => new Element(tag),
  createTextNode: text => new Element('#text', text),
  querySelector: selector => { if (!controls.has(selector)) controls.set(selector, new Element('control')); return controls.get(selector); },
};
const page = fs.readFileSync(path.join(__dirname, '../gui/index.html'), 'utf8');
const source = page.match(/<script>([\s\S]*?)<\/script>/)[1].split('// -------------------------------------------------------------------- boot')[0];
const context = vm.createContext({document, console, setTimeout});
vm.runInContext(source + `
globalThis.ui = { nextStep, reasoningMap, canvasModel, setup(state, derived) {
  SELECTED = null; VIEW = {state, derived}; CURRENT = state.id;
  META = {operator: {role: 'decision_owner'}, vocabulary: {statement_roles:['observation','question'], line_reason_codes:['insufficient_evidence','duplicate']}};
}};`, context);
const {ui} = context;
const state = {id:'sess_test', phase:'intake', revision:1, statements:[{id:'stmt_1', text:'<img src=x onerror=alert(1)>', primary_role:'question', status:'draft', provenance:{kind:'sourced', source_ids:['art_chat']}}], frames:[], graph:{nodes:[], edges:[]}, approvals:[]};
const derived = {unclassified:[], abstraction_required:false, frame_set:{selectable:true}, ladder_order:[], gates:[{gate:'intake_correction', targets:['stmt_1'], authority:['decision_owner']}]};
ui.setup(state, derived);
let tree = ui.reasoningMap(state);
assert.match(tree.textContent, /not causal claims/);
assert.match(tree.textContent, /<img src=x onerror=alert\(1\)>/);
assert.equal(tree.all('img').length, 0, 'source content must remain text');
assert.equal(tree.querySelectorAll('[data-item]').length, 1);
assert.equal(ui.nextStep(state, derived).all('button').length, 1);
ui.setup(state, {...derived, unclassified:['stmt_1']});
assert.equal(ui.nextStep(state, {...derived, unclassified:['stmt_1']}).all('button').length, 0, 'unclassified intake must not offer continuation');
ui.setup(state, derived);
tree = ui.reasoningMap(state);
tree.querySelectorAll('[data-item]')[0].events.click();
assert.match(tree.textContent, /Basis: sourced/);

const causal = {...state, phase:'causal', graph:{nodes:[
  {id:'node_a', type:'outcome', label:'Margin', status:'proposed'},
  {id:'node_b', type:'hypothesis', label:'Supplier power', status:'proposed'},
  {id:'node_c', type:'evidence', label:'Counter-evidence', status:'draft'},
  {id:'node_d', type:'risk', label:'Disconnected risk', status:'proposed'},
], edges:[
  {id:'edge_1', source:'node_b', target:'node_a', type:'contributes_to', status:'proposed'},
  {id:'edge_2', source:'node_a', target:'node_b', type:'contributes_to', status:'proposed'},
  {id:'edge_3', source:'node_c', target:'node_b', type:'contradicts', status:'proposed'},
]}};
ui.setup(causal, derived);
tree = ui.reasoningMap(causal);
const buttons = tree.querySelectorAll('[data-item]');
for (const id of ['node_a','node_b','node_c','node_d']) assert(buttons.some(b => b.attrs['data-item'] === id), `missing ${id}`);
assert(buttons.length < 10, 'cycle expansion must terminate');
assert.equal(buttons.length, 4, 'a cyclic graph must draw each node once');
assert(!tree.textContent.includes('Hypotheses & mechanisms'), 'background category headings must not be rendered');
assert(buttons.every(b => b.children[0].textContent.includes(b.attrs['data-type'])), 'each card identifies its type');
assert.equal(tree.all('path').filter(p => p.attrs['data-edge']).length, 3, 'every recorded edge is drawn');
buttons.find(b => b.attrs['data-item'] === 'node_b').events.click();
assert.match(tree.textContent, /Counter-evidence → contradicts → Supplier power/);
assert.match(tree.textContent, /Supplier power → contributes to → Margin/);
const saved = JSON.stringify(causal);
const before = buttons[0].style.left;
buttons[0].events.keydown({key:'ArrowRight',preventDefault(){},stopPropagation(){}});
assert.notEqual(buttons[0].style.left, before, 'keyboard movement changes the card position');
assert.equal(JSON.stringify(causal), saved, 'layout movement must not modify canonical state');
assert.equal(ui.canvasModel(causal).edges.length, 3);

// ADR-0031 and ADR-0032: band, broken and parked ground, solid ground, challenges and lines.
const profile = (band, extra = {}) => ({band, bases:{fact:[], inference:[], opinion:[], gap:[]}, undecided:[], broken:[], parked:[],
  challenges:{open:[], answered_by_fact:[], answered_by_opinion:[], conceded:[]}, upstream_open:[], weakest:null, ...extra});
const grounded = {...causal, status:'active',
  graph:{nodes:[...causal.graph.nodes.slice(0, 3), {...causal.graph.nodes[3], status:'rejected'}], edges:causal.graph.edges},
  challenges:[{id:'chal_001', target_id:'node_b', objection:'One supplier only.', actor:{id:'svc_reasoner', kind:'service'}, status:'open'}],
  lines:[{id:'line_001', anchor_id:'node_a', tip_ids:['node_b'], node_ids:['node_b'], reason_code:'insufficient_evidence', reason:'No quote at volume.', actor:{id:'user_1', kind:'human'}, status:'parked'}]};
const groundedDerived = {...derived, grounding:{nodes:{node_a:profile('solid'), node_b:profile('weak', {challenges:{open:['chal_001'], answered_by_fact:[], answered_by_opinion:[], conceded:[]}}), node_c:profile('mixed'), node_d:profile('weak', {broken:['node_d']})}, solid_ground:['node_a']}};
ui.setup(grounded, groundedDerived);
tree = ui.reasoningMap(grounded);
const cards = new Map(tree.querySelectorAll('[data-item]').map(b => [b.attrs['data-item'], b]));
assert.deepEqual(['node_a','node_b','node_c','node_d'].map(id => cards.get(id).attrs['data-band']), ['solid','weak','mixed','weak'], 'each card carries its band');
assert(cards.get('node_d').className.includes('broken'), 'broken ground is outlined');
assert(cards.get('node_b').className.includes('parked'), 'a parked line is greyed');
assert(cards.get('node_a').className.includes('solid-ground'), 'solid ground is highlighted');
assert.match(cards.get('node_a').attrs['aria-label'], /solid ground, a suggested restart anchor/);
assert.match(tree.textContent, /Grounding, challenges and parked lines as a list/);
assert.match(tree.textContent, /Solid ground \(suggested restart anchors\): node_a/);
assert.match(tree.textContent, /line_001 from node_a to node_b: insufficient evidence/);
assert.equal(tree.all('button').filter(b => b.textContent.includes('Reopen')).length, 1, 'the list offers Reopen on a parked line');
cards.get('node_b').events.click();
for (const text of [/Grounding: weak/, /chal_001 on node_b: One supplier only/, /Raise challenge/, /Answer/, /Concede/, /Park line…/, /Park line/, /Reopen/])
  assert.match(tree.textContent, text);
tree.all('button').find(b => b.attrs['data-list-item'] === 'node_c').events.click();
assert.match(tree.textContent, /Grounding: mixed/, 'the list opens the same inspector');
assert.equal(JSON.stringify(grounded).includes('"band"'), false, 'grounding is never written into state');
console.log('PASS card type labels, no background groups, source-text escaping, blocked continuation, node inspection, cycle edges, disconnected nodes, contradiction links, layout-only movement, grounding bands, broken and parked ground, solid ground, challenge and line actions, and the list equivalent');
