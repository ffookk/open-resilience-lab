/* Pure schema, import, state and export logic shared by the offline UI and tests. */
(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = factory;
  else root.PlanStudio = factory(root.PLAN_STUDIO_POLICY);
})(globalThis, function (policy) {
  "use strict";
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const clone = value => JSON.parse(JSON.stringify(value));
  const points = value => Array.from(value);
  const whitespace = new Set(policy.whitespace);
  const hasSpace = value => points(value).some(c => whitespace.has(c.codePointAt(0)));
  const fail = () => { throw new Error("The file must contain strict UTF-8 JSON without duplicate keys or unsupported numeric values."); };
  function parseJSON(source) {
    if (typeof source !== "string" || new TextEncoder().encode(source).length > policy.max_bytes) throw new Error("The JSON input exceeds the supported size limit.");
    let cursor = 0;
    const space = () => {while (/[ \t\r\n]/.test(source[cursor] || "!")) cursor++;};
    function string() {
      const start = cursor++;
      while (cursor < source.length) {
        const character = source[cursor++];
        if (character === "\\") cursor++;
        else if (character === '"') {
          try {return JSON.parse(source.slice(start, cursor));} catch (_) {fail();}
        }
      }
      fail();
    }
    function value(depth) {
      if (depth > 12) fail();
      space(); const character = source[cursor];
      if (character === '"') return string();
      if (character === "{") {
        cursor++; space(); const result = Object.create(null);
        if (source[cursor] === "}") {cursor++; return result;}
        while (true) {
          space(); if (source[cursor] !== '"') fail();
          const key = string(); if (own(result, key)) fail();
          space(); if (source[cursor++] !== ":") fail();
          result[key] = value(depth + 1); space();
          const end = source[cursor++]; if (end === "}") return result; if (end !== ",") fail();
        }
      }
      if (character === "[") {
        cursor++; space(); const result = [];
        if (source[cursor] === "]") {cursor++; return result;}
        while (true) {
          result.push(value(depth + 1)); space();
          const end = source[cursor++]; if (end === "]") return result; if (end !== ",") fail();
        }
      }
      for (const [literal, result] of [["true", true], ["false", false], ["null", null]]) {
        if (source.startsWith(literal, cursor)) {cursor += literal.length; return result;}
      }
      const match = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(source.slice(cursor));
      if (!match) fail();
      cursor += match[0].length;
      // Schema v1 has one integer field and no floating-point fields. Preserve that distinction.
      if (/[.eE]/.test(match[0])) fail();
      const number = Number(match[0]); if (!Number.isSafeInteger(number)) fail(); return number;
    }
    const result = value(0); space(); if (cursor !== source.length) fail(); return result;
  }
  function validDate(value) {
    if (typeof value !== "string" || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value)) return false;
    const [year, month, day] = value.split("-").map(Number);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    return year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= [31, leap ? 29 : 28, 31,30,31,30,31,31,30,31,30,31][month - 1];
  }
  function ipv6(value) {
    const scoped = value.split("%");
    if (scoped.length > 2 || scoped.length === 2 && !scoped[1]) return false;
    let address = scoped[0];
    if (address.includes(".")) {
      const at = address.lastIndexOf(":"), tail = address.slice(at + 1).split(".");
      if (tail.length !== 4 || tail.some(n => !/^(?:0|[1-9][0-9]{0,2})$/.test(n) || Number(n) > 255)) return false;
      address = address.slice(0, at + 1) + "0:0";
    }
    const sides = address.split("::"); if (sides.length > 2) return false;
    const groups = sides.flatMap(s => s === "" ? [] : s.split(":"));
    return groups.every(s => /^[0-9a-fA-F]{1,4}$/.test(s)) && (sides.length === 2 ? groups.length < 8 : groups.length === 8);
  }
  function validURL(value) {
    if (typeof value !== "string" || hasSpace(value) || value.includes("\\")) return false;
    const match = /^https:\/\/([^/?#]*)([^?#]*)(?:\?([^#]*))?(?:#(.*))?$/i.exec(value);
    if (!match || !match[1] || match[3] || match[4] || match[1].includes("@")) return false;
    const authority = match[1];
    const normalized = authority.replace(/[@:#?]/g, "").normalize("NFKC");
    if (/[/?#@:]/.test(normalized)) return false;
    let host, port = "";
    if (authority.includes("[") || authority.includes("]")) {
      const bracket = /^(.*?)\[([^\]]*)\](.*)$/.exec(authority); if (!bracket) return false;
      if (policy.strict_brackets && (bracket[1] || bracket[3] && !bracket[3].startsWith(":"))) return false;
      host = bracket[2];
      const suffix = bracket[3], colon = suffix.indexOf(":");
      port = colon < 0 ? "" : suffix.slice(colon + 1);
      if (!(host.startsWith("v") ? /^v[0-9a-fA-F]+\..+$/.test(host) : ipv6(host))) return false;
    } else {
      const colon = authority.indexOf(":");
      host = colon < 0 ? authority : authority.slice(0, colon);
      port = colon < 0 ? "" : authority.slice(colon + 1);
    }
    return Boolean(host) && (!port || /^[0-9]+$/.test(port) && Number(port) <= 65535);
  }
  function validate(plan) {
    const errors = [];
    const error = (path, message) => errors.push({path, message});
    function object(value, path, required, optional = []) {
      if (!value || typeof value !== "object" || Array.isArray(value)) {error(path, "Expected an object."); return false;}
      if (required.some(key => !own(value, key)) || Object.keys(value).some(key => !required.includes(key) && !optional.includes(key))) error(path, "Missing or unsupported fields.");
      return true;
    }
    function text(value, path, limit) {
      if (typeof value !== "string" || !points(value).some(c => !whitespace.has(c.codePointAt(0))) || points(value).length > limit) {error(path, "Enter nonempty text within the displayed character limit."); return false;}
      if (points(value).some(c => {const n = c.codePointAt(0); return n < 32 && n !== 9 && n !== 10 || n === 127 || n >= 0xd800 && n <= 0xdfff;})) {error(path, "Unsupported control characters or unmatched Unicode surrogates."); return false;}
      return true;
    }
    function date(value, path) {if (!validDate(value)) error(path, "Enter a valid calendar date in YYYY-MM-DD format.");}
    function list(key, minimum, maximum, required, optional, fields) {
      if (!own(plan, key) && minimum === 0) return;
      const values = plan[key];
      if (!Array.isArray(values)) {error([key], "Expected a list."); return;}
      if (values.length < minimum || values.length > maximum) error([key], "Entry count is outside the displayed range.");
      values.forEach((item, index) => {
        const path = [key, index];
        if (!object(item, path, required, optional)) return;
        fields.forEach(([field, limit]) => {if (required.includes(field) || own(item, field)) text(item[field], [...path, field], limit);});
        if (key === "sources") {
          if (typeof item.url === "string" && !validURL(item.url)) error([...path, "url"], "Use HTTPS without credentials, a query, a fragment, whitespace, or an invalid port.");
          date(item.verified_on, [...path, "verified_on"]);
        }
      });
    }
    if (!object(plan, [], ["schema_version", "title", "region", "reviewed_on", "contacts", "meeting_points"], ["household", "notes", "sources"])) return errors;
    if (typeof plan.schema_version !== "number" || !Number.isInteger(plan.schema_version) || plan.schema_version !== 1) error(["schema_version"], "Only integer schema version 1 is supported.");
    text(plan.title, ["title"], policy.limits.title); text(plan.region, ["region"], policy.limits.region); date(plan.reviewed_on, ["reviewed_on"]);
    list("contacts", 1, 20, ["name", "role", "contact"], [], [["name", 200], ["role", 200], ["contact", 200]]);
    list("meeting_points", 1, 10, ["label", "instructions"], [], [["label", 120], ["instructions", 2000]]);
    list("household", 0, 20, ["name"], ["needs"], [["name", 120], ["needs", 1000]]);
    list("sources", 0, 20, ["title", "url", "verified_on"], [], [["title", 200], ["url", 2000]]);
    if (own(plan, "notes")) text(plan.notes, ["notes"], policy.limits.notes);
    return errors;
  }
  function importJSON(source) {
    const plan = parseJSON(source);
    if (validate(plan).length) throw new Error("The imported file does not match plan schema version 1. The current draft was kept.");
    return clone(plan);
  }
  function importBytes(bytes) {
    if (bytes.byteLength > policy.max_bytes) throw new Error("The JSON input exceeds the supported size limit.");
    return importJSON(new TextDecoder("utf-8", {fatal:true, ignoreBOM:true}).decode(bytes));
  }
  function exportJSON(plan) {
    if (validate(plan).length) throw new Error("Fix the validation errors before exporting.");
    const pretty = JSON.stringify(plan, null, 2) + "\n";
    if (new TextEncoder().encode(pretty).length <= policy.max_bytes) return pretty;
    const compact = JSON.stringify(plan);
    if (new TextEncoder().encode(compact).length > policy.max_bytes) throw new Error("The exported plan exceeds the 256 KiB input limit.");
    return compact;
  }
  const blankItem = key => ({contacts:{name:"", role:"", contact:""}, meeting_points:{label:"", instructions:""}, household:{name:""}, sources:{title:"", url:"", verified_on:""}}[key]);
  const blank = () => ({schema_version:1, title:"", region:"", reviewed_on:"", contacts:[blankItem("contacts")], meeting_points:[blankItem("meeting_points")]});
  class Draft {
    constructor(plan = blank()) {this.plan = clone(plan); this.baseline = JSON.stringify(this.plan); this.revision = 0; this.pending = null;}
    get dirty() {return JSON.stringify(this.plan) !== this.baseline;}
    changed() {this.revision++; this.pending = null;}
    set(path, value) {
      let target = this.plan; for (const key of path.slice(0, -1)) target = target[key];
      target[path[path.length - 1]] = value; this.changed();
    }
    optional(path, include, initial) {
      let target = this.plan; for (const key of path.slice(0, -1)) target = target[key];
      if (include) target[path.at(-1)] = clone(initial); else delete target[path.at(-1)]; this.changed();
    }
    add(key) {if (!Array.isArray(this.plan[key]) || this.plan[key].length >= (key === "meeting_points" ? 10 : 20)) return false; this.plan[key].push(blankItem(key)); this.changed(); return true;}
    duplicate(key, index) {
      const values = this.plan[key], maximum = key === "meeting_points" ? 10 : 20;
      if (!Array.isArray(values) || !Number.isInteger(index) || index < 0 || index >= values.length || values.length >= maximum) return false;
      values.splice(index + 1, 0, clone(values[index])); this.changed(); return true;
    }
    remove(key, index) {this.plan[key].splice(index, 1); this.changed();}
    move(key, index, delta) {const values = this.plan[key], next = index + delta; if (next < 0 || next >= values.length) return false; [values[index], values[next]] = [values[next], values[index]]; this.changed(); return true;}
    moveTo(key, index, destination) {
      const values = this.plan[key];
      if (!Array.isArray(values) || !Number.isInteger(index) || !Number.isInteger(destination) || index < 0 || index >= values.length || destination < 0 || destination >= values.length || index === destination) return false;
      values.splice(destination, 0, values.splice(index, 1)[0]); this.changed(); return true;
    }
    import(source) {const next = importJSON(source); this.plan = next; this.baseline = JSON.stringify(next); this.changed();}
    reset() {this.plan = blank(); this.baseline = JSON.stringify(this.plan); this.changed();}
    requestJSON() {const output = exportJSON(this.plan); this.pending = JSON.stringify(this.plan); return output;}
    confirmSaved() {if (this.pending === JSON.stringify(this.plan)) {this.baseline = this.pending; this.pending = null; return true;} return false;}
  }
  function sections(plan, cards = false) {
    const result = [
      {heading:"Contacts", entries:(plan.contacts || []).map(item => ({title:item.name, text:"Role: " + item.role + "\nContact: " + item.contact}))},
      {heading:"Agreed meeting arrangements", entries:(plan.meeting_points || []).map(item => ({title:item.label, text:item.instructions}))}
    ];
    if (!cards) {
      result.push({heading:"Household and support needs", entries:(plan.household || []).map(item => ({title:item.name, text:own(item,"needs") ? item.needs : "Not provided"}))});
      result.push({heading:"Household notes", entries:own(plan,"notes") ? [{title:"Notes", text:plan.notes}] : []});
      result.push({heading:"Sources entered by the author", entries:(plan.sources || []).map(item => ({title:item.title, text:item.url + "\nUser-supplied source review date: " + item.verified_on}))});
    }
    return result;
  }
  const escape = value => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#x27;"}[c]));
  function exportHTML(plan, cards = false) {
    exportJSON(plan);
    const title = cards ? "Private contact and meeting cards" : "Private household plan";
    const articles = sections(plan, cards).map(section => '<section><h2>' + section.heading + '</h2><div class="entries">' + (section.entries.length ? section.entries.map(item => '<article><h3 dir="auto">' + escape(item.title) + '</h3><p dir="auto">' + escape(item.text) + '</p>' + (cards ? '<footer>' + escape(plan.title) + '\nUser-supplied household review date: ' + escape(plan.reviewed_on) + '</footer>' : '') + '</article>').join('') : '<p>Not provided</p>') + '</div></section>').join('');
    return '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="' + escape(policy.export_csp) + '"><meta name="referrer" content="no-referrer"><title>' + title + '</title><style>' + policy.export_css + '</style></head><body class="' + (cards ? 'cards' : 'full') + '"><header><p>PRIVATE LOCAL EXPORT</p><h1 dir="auto">' + escape(plan.title) + '</h1>' + (cards ? '' : '<p dir="auto">Region: ' + escape(plan.region) + '</p>') + '<p>User-supplied household review date: ' + escape(plan.reviewed_on) + '</p><p>' + (cards ? 'Contacts and meeting arrangements only. Consult the full plan for other information. Cards expand; preview pagination before printing or cutting.' : 'This file organizes household decisions. It does not provide medical advice, factual verification, or disaster safety certification.') + '</p></header><main>' + articles + '</main><footer>Keep all files and printouts private. Source text and review dates remain user supplied.</footer></body></html>\n';
  }
  return Object.freeze({parseJSON, validate, importJSON, importBytes, exportJSON, exportHTML, sections, validDate, validURL, blank, Draft, clone, policy});
});
