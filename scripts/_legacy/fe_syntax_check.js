// fe_syntax_check.js — cek cepat sintaks JSX (tanpa build penuh).
// Pakai: cd /app/frontend && node /app/scripts/fe_syntax_check.js src/**/file.jsx
const path = require("path");
const babel = require(path.join("/app/frontend/node_modules/@babel/core"));
const fs = require("fs");
const files = process.argv.slice(2);
let bad = 0;
for (const f of files) {
  try {
    babel.parseSync(fs.readFileSync(f, "utf8"), {
      filename: f,
      presets: [path.join("/app/frontend/node_modules/@babel/preset-react")],
      configFile: false, babelrc: false,
    });
    console.log("OK  " + f);
  } catch (e) { bad++; console.log("ERR " + f + " :: " + e.message.split("\n")[0]); }
}
process.exit(bad ? 1 : 0);
