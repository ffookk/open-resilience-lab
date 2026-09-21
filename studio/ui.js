/* Browser controller. Every household value is assigned through textContent or value. */
(function () {
  "use strict";
  const api = globalThis.PlanStudio, draft = new api.Draft();
  const byId = id => document.getElementById(id);
  const form = byId("plan-form"), preview = byId("preview-content"), status = byId("draft-status");
  let showErrors = false, importSequence = 0;
  const labels = {title:"Plan title", region:"Applicable region", reviewed_on:"Household review date (user supplied)",
    contacts:"Contacts", meeting_points:"Meeting arrangements", household:"Household members", sources:"Sources", notes:"Household notes",
    name:"Name", role:"Agreed role", contact:"Contact details", label:"Arrangement label", instructions:"Agreed instructions",
    needs:"Necessary support needs", url:"HTTPS source URL", verified_on:"Source review date (user supplied)"};
  const pathId = path => "field-" + path.join("-");
  const node = (tag, text, className) => {const element = document.createElement(tag); if (text !== undefined) element.textContent = text; if (className) element.className = className; return element;};
  const button = (text, handler, className = "secondary") => {const element = node("button", text, className); element.type = "button"; element.addEventListener("click", handler); return element;};
  const message = text => {byId("operation-status").textContent = text;};
  function field(parent, path, value, limit, date = false) {
    const wrapper = node("div", undefined, "field"), id = pathId(path);
    const label = node("label", path[0] === "sources" && path.at(-1) === "title" ? "Source title" : labels[path.at(-1)] || "Text"); label.htmlFor = id;
    const input = node(date ? "input" : "textarea"); input.id = id; input.name = id;
    if (date) {input.type = "text"; input.placeholder = "YYYY-MM-DD"; input.inputMode = "numeric";}
    else input.rows = limit > 200 ? 3 : 2;
    input.value = value; input.autocomplete = "off"; input.spellcheck = false; input.dir = "auto";
    input.setAttribute("aria-describedby", id + "-help");
    const hint = node("p", undefined, "hint"); hint.id = id + "-help";
    const updateCount = () => {hint.textContent = date ? "Enter the actual review date after household or source review. No date is inserted automatically." : Array.from(input.value).length + " / " + limit + " characters. Newlines and tabs are preserved.";};
    input.addEventListener("input", () => {draft.set(path, input.value); updateCount(); changed();});
    updateCount(); wrapper.append(label, input, hint); parent.append(wrapper);
  }
  function toggle(parent, text, path, present, initial, rerender = true) {
    const label = node("label", undefined, "toggle"), control = node("input"); control.type = "checkbox"; control.checked = present;
    control.id = "include-" + path.join("-");
    control.addEventListener("change", () => {draft.optional(path, control.checked, initial); if (rerender) renderForm(); changed(); const target = byId(control.id); if (target) target.focus();});
    label.append(control, document.createTextNode(text)); parent.append(label);
  }
  function section(key, heading, description) {
    const item = node("section", undefined, "editor-section"); item.id = "section-" + key;
    item.setAttribute("aria-labelledby", "heading-" + key);
    const title = node("h2", heading); title.id = "heading-" + key;
    item.append(title, node("p", description, "hint")); form.append(item); return item;
  }
  function list(key, fields, minimum, maximum) {
    const parent = section(key, labels[key], "Entries: " + (draft.plan[key] || []).length + ". Allowed: " + minimum + "-" + maximum + ". Use the move buttons to change order.");
    if (minimum === 0) toggle(parent, "Include " + labels[key].toLowerCase() + " in JSON", [key], Object.hasOwn(draft.plan, key), []);
    if (!Object.hasOwn(draft.plan, key)) return;
    const entries = draft.plan[key];
    entries.forEach((item, index) => {
      const box = node("fieldset", undefined, "entry"); box.append(node("legend", labels[key] + " " + (index + 1)));
      fields.forEach(([name, limit, date]) => field(box, [key, index, name], item[name], limit, date));
      if (key === "household") {
        toggle(box, "Include necessary support needs", [key, index, "needs"], Object.hasOwn(item, "needs"), "");
        if (Object.hasOwn(item, "needs")) field(box, [key, index, "needs"], item.needs, 1000);
      }
      const actions = node("div", undefined, "entry-actions");
      for (const [text, delta] of [["Move up", -1], ["Move down", 1]]) {
        const move = button(text, () => {
          if (draft.move(key, index, delta)) {renderForm(); changed(); byId(pathId([key, index + delta, fields[0][0]])).focus();}
        }); move.disabled = index + delta < 0 || index + delta >= entries.length;
        move.setAttribute("aria-label", text + ": " + labels[key] + " " + (index + 1)); actions.append(move);
      }
      const remove = button("Remove", () => {draft.remove(key, index); renderForm(); changed(); byId("add-" + key).focus();}, "danger");
      remove.setAttribute("aria-label", "Remove " + labels[key] + " " + (index + 1)); actions.append(remove); box.append(actions); parent.append(box);
    });
    const add = button("Add " + {contacts:"contact", meeting_points:"meeting arrangement", household:"household member", sources:"source"}[key], () => {
      if (draft.add(key)) {renderForm(); changed(); byId(pathId([key, draft.plan[key].length - 1, fields[0][0]])).focus();}
    }); add.id = "add-" + key; add.disabled = entries.length >= maximum; parent.append(add);
  }
  function renderForm() {
    form.replaceChildren();
    const basics = section("basics", "Plan details", "A blank draft is incomplete. Enter only arrangements already agreed by your household; format checks are not independent review.");
    field(basics, ["title"], draft.plan.title, 120); field(basics, ["region"], draft.plan.region, 120); field(basics, ["reviewed_on"], draft.plan.reviewed_on, 10, true);
    list("contacts", [["name",200],["role",200],["contact",200]], 1,20);
    list("meeting_points", [["label",120],["instructions",2000]], 1,10);
    list("household", [["name",120]], 0,20);
    const notes = section("notes", "Household notes", "Optional fields retain their presence or absence. Included text must be nonempty; exclude it to omit it from JSON.");
    toggle(notes, "Include household notes in JSON", ["notes"], Object.hasOwn(draft.plan, "notes"), "");
    if (Object.hasOwn(draft.plan, "notes")) field(notes, ["notes"], draft.plan.notes, 4000);
    list("sources", [["title",200],["url",2000],["verified_on",10,true]], 0,20);
  }
  function renderPreview() {
    preview.replaceChildren();
    const title = node("h3", draft.plan.title || "Untitled draft"); title.dir = "auto";
    preview.append(title, node("p", "Region: " + (draft.plan.region || "Not entered")), node("p", "User-supplied household review date: " + (draft.plan.reviewed_on || "Not entered")));
    api.sections(draft.plan).forEach((section, index) => {
      if (byId("preview-section").value !== "all" && byId("preview-section").value !== String(index)) return;
      const block = node("section"); block.append(node("h4", section.heading));
      if (!section.entries.length) block.append(node("p", "Not provided", "hint"));
      section.entries.forEach(item => {const card = node("article", undefined, "preview-card"); const heading = node("h5", item.title || "Untitled entry"), body = node("p", item.text); heading.dir = body.dir = "auto"; card.append(heading, body); block.append(card);});
      preview.append(block);
    });
  }
  function focusPath(path) {
    const input = byId(pathId(path));
    if (input) input.focus();
    else {const target = byId("section-" + path[0]) || form; target.tabIndex = -1; target.focus();}
  }
  function renderErrors(errors) {
    const box = byId("validation-errors"); box.replaceChildren(); box.hidden = !showErrors || !errors.length;
    form.querySelectorAll("[aria-invalid]").forEach(input => input.removeAttribute("aria-invalid"));
    if (!showErrors || !errors.length) return;
    box.append(node("h3", "Review these fields"));
    const list = node("ul");
    errors.forEach(error => {
      const item = node("li"), path = error.path;
      const name = path.map(part => typeof part === "number" ? String(part + 1) : (part === "title" && path[0] === "sources" ? "Source title" : labels[part] || "Plan")).join(" / ") || "Plan";
      item.append(button(name + ": " + error.message, () => focusPath(path), "error-link")); list.append(item);
      const input = byId(pathId(path)); if (input) input.setAttribute("aria-invalid", "true");
    }); box.append(list);
  }
  function changed() {
    const errors = api.validate(draft.plan);
    status.textContent = draft.dirty ? "Unsaved edits in this tab" : "No edits since import, reset, or confirmed JSON save";
    status.dataset.dirty = String(draft.dirty);
    byId("validation-status").textContent = errors.length ? "Incomplete draft: " + errors.length + " format issue(s). Review fields before export." : "Schema format checks pass. Household decisions and source facts remain unverified.";
    ["export-json", "export-html", "export-cards"].forEach(id => byId(id).disabled = errors.length > 0);
    byId("confirm-saved").disabled = draft.pending === null;
    renderErrors(errors); renderPreview();
  }
  function download(content, type, filename) {
    const objectURL = URL.createObjectURL(new Blob([content], {type}));
    try {
      const link = node("a"); link.href = objectURL; link.download = filename; document.body.append(link); link.click(); link.remove();
    } finally {setTimeout(() => URL.revokeObjectURL(objectURL), 30000);}
  }
  byId("validate").addEventListener("click", () => {
    showErrors = true; changed(); const errors = api.validate(draft.plan);
    if (errors.length) {byId("validation-errors").focus();} else message("Format checks passed. This does not verify household arrangements, source facts, or safety.");
  });
  byId("preview-section").addEventListener("change", renderPreview);
  byId("toggle-preview").addEventListener("click", event => {
    const panel = byId("preview-panel"); panel.hidden = !panel.hidden;
    event.currentTarget.textContent = panel.hidden ? "Show live preview" : "Hide live preview";
    event.currentTarget.setAttribute("aria-expanded", String(!panel.hidden));
    document.querySelector(".layout").classList.toggle("preview-hidden", panel.hidden);
  });
  byId("first-issue").addEventListener("click", () => {
    showErrors = true; changed(); const errors = api.validate(draft.plan);
    if (errors.length) focusPath(errors[0].path); else message("No format issues to focus. Household decisions and source facts remain unverified.");
  });
  byId("reset").addEventListener("click", () => {
    if (!window.confirm("Discard the current draft and start a blank plan? No backup is saved automatically.")) return;
    importSequence++; draft.reset(); showErrors = false; byId("import-json").value = ""; renderForm(); changed(); message("Blank draft started. No date or review status has been assumed."); byId("field-title").focus();
  });
  byId("import-json").addEventListener("change", async event => {
    const file = event.target.files[0]; if (!file) return;
    const sequence = ++importSequence, revision = draft.revision;
    try {
      if (file.size > api.policy.max_bytes) throw new Error("limit");
      const raw = await file.arrayBuffer();
      if (sequence !== importSequence) return;
      if (revision !== draft.revision) {message("The draft changed while the import was being read. Select the file again to import it."); return;}
      const imported = api.importBytes(raw);
      const source = api.exportJSON(imported);
      if (draft.dirty && !window.confirm("Replace unsaved edits with this validated JSON file? No backup is saved automatically.")) {message("Import cancelled. The current draft was kept."); return;}
      draft.import(source); showErrors = false; renderForm(); changed(); message("JSON imported locally. All fields and optional-field presence were preserved; facts remain unverified."); byId("field-title").focus();
    } catch (_) {message("Import failed. Use a valid UTF-8 schema-version-1 JSON file up to 256 KiB without duplicate keys. The current draft was kept.");}
    finally {if (sequence === importSequence) event.target.value = "";}
  });
  byId("export-json").addEventListener("click", () => {
    try {const content = draft.requestJSON(); download(content, "application/json", "household-plan.json"); changed(); message("JSON download requested. Check that the complete file was saved privately, then use I saved the JSON to clear the unsaved indicator.");}
    catch (_) {draft.pending = null; changed(); message("JSON export failed. Review the plan and its size; no save is confirmed.");}
  });
  byId("confirm-saved").addEventListener("click", () => {if (draft.confirmSaved()) {changed(); message("JSON save confirmed by you. Keep the downloaded file and all printouts private.");}});
  for (const [id, cards] of [["export-html",false],["export-cards",true]]) {
    byId(id).addEventListener("click", () => {
      try {download(api.exportHTML(draft.plan, cards), "text/html", cards ? "household-cards.html" : "household-plan.html"); message("Printable HTML download requested. Preview pagination before printing. This does not save the editable JSON or clear unsaved edits.");}
      catch (_) {message("Printable export failed. Validate the plan and check its size before exporting.");}
    });
  }
  window.addEventListener("beforeunload", event => {if (draft.dirty) {event.preventDefault(); event.returnValue = "";}});
  form.addEventListener("submit", event => event.preventDefault());
  renderForm(); changed();
})();
