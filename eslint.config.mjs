// ESLint for the app's scripts and the website's (npm run lint). They are classic scripts, with no modules and
// no build step: the scripts of a page share one global scope, so what one script declares at its top level,
// or hands out as window.A2…, is a global to the others. Those names are read here from the scripts themselves.
import { readFileSync, readdirSync } from "node:fs";
import js from "@eslint/js";
import * as espree from "espree";
import globals from "globals";

const STATIC = "aion2calc/app/static";
const VENDORED = `${STATIC}/html2canvas.min.js`;
const scripts = (dir) =>
  readdirSync(dir)
    .filter((f) => f.endsWith(".js"))
    .map((f) => `${dir}/${f}`)
    .filter((f) => f !== VENDORED);
// A script that does not parse adds no names here; ESLint then reports its parsing error, as for any script.
const parse = (file) => {
  try {
    return espree.parse(readFileSync(file, "utf8"), { ecmaVersion: 2022, sourceType: "script" });
  } catch {
    return { type: "Program", body: [] };
  }
};

// The names scripts declare at their top level: a const, function or class is read-only to the others, a let
// or var writable.
function declared(files) {
  const names = {};
  for (const file of files)
    for (const node of parse(file).body) {
      if (node.type === "FunctionDeclaration" || node.type === "ClassDeclaration") names[node.id.name] = "readonly";
      if (node.type === "VariableDeclaration")
        for (const d of node.declarations)
          if (d.id.type === "Identifier") names[d.id.name] = node.kind === "const" ? "readonly" : "writable";
    }
  return names;
}

// What the modules hand out (window.A2Raid = …), which a page reaches as window.A2Raid or A2Raid.
function handedOut(files) {
  const names = {};
  const visit = (node) => {
    if (!node || typeof node.type !== "string") return;
    const left = node.type === "AssignmentExpression" ? node.left : null;
    if (
      left &&
      left.type === "MemberExpression" &&
      !left.computed &&
      left.object.type === "Identifier" &&
      left.object.name === "window"
    )
      names[left.property.name] = "readonly";
    for (const value of Object.values(node))
      if (Array.isArray(value)) value.forEach(visit);
      else if (value && typeof value.type === "string") visit(value);
  };
  for (const file of files) visit(parse(file));
  return names;
}

// app.js and the pages share their names; the modules (also used by the website) and the website's scripts may
// rely only on what the modules hand out, as app.js is not on the website's pages.
const app = [`${STATIC}/app.js`, ...scripts(`${STATIC}/pages`)];
const modules = scripts(STATIC).filter((f) => f !== `${STATIC}/app.js`);
const site = scripts("site");

export default [
  { ignores: [VENDORED, "build/**", "dist/**"] },
  js.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: { ...globals.browser, ...handedOut([...modules, ...site]) },
    },
    rules: {
      "no-empty": ["error", { allowEmptyCatch: true }], // storage that may be blocked is tried, not needed
      "no-redeclare": ["error", { builtinGlobals: false }], // a script declares the names the others use
      "no-unused-vars": ["error", { vars: "local", args: "none", caughtErrors: "none", ignoreRestSiblings: true }],
    },
  },
  { files: app, languageOptions: { globals: declared(app) } },
  { files: site, languageOptions: { globals: declared(site) } },
  { files: ["eslint.config.mjs"], languageOptions: { sourceType: "module", globals: globals.node } },
];
