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
  META = {operator: {role: 'decision_owner'}, vocabulary: {statement_roles:['observation','question']}};
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
console.log('PASS card type labels, no background groups, source-text escaping, blocked continuation, node inspection, cycle edges, disconnected nodes, contradiction links and layout-only movement');
