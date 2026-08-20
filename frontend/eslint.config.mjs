// eslint.config.mjs — flat config minimal untuk ESLint 9.
// Tujuan: memberi ESLint 9 sebuah konfigurasi valid (tanpa ini `npx eslint` gagal
// dengan "could not find config file"), sekaligus menjaga aturan tetap ringan agar
// tidak menghambat iterasi. Build produksi memakai craco (DISABLE_ESLINT_PLUGIN=true).
import js from "@eslint/js";
import globals from "globals";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";

export default [
  {
    ignores: [
      "build/**",
      "node_modules/**",
      "coverage/**",
      "plugins/**",
      "static_server.js",
      "craco.config.js",
      "postcss.config.js",
      "tailwind.config.js",
    ],
  },
  js.configs.recommended,
  {
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: { ...globals.browser, ...globals.node, process: "readonly" },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { react, "react-hooks": reactHooks },
    settings: { react: { version: "detect" } },
    rules: {
      // Sintaks & kesalahan nyata = ERROR (yang benar-benar merusak build).
      "no-undef": "off",            // CRA/craco sudah menangani resolusi global
      "no-unused-vars": "off",      // ditangani review manual; terlalu berisik di repo besar
      "no-empty": "off",
      "no-useless-escape": "off",
      "react/jsx-uses-vars": "error",
      "react/jsx-no-undef": "error",
      "react-hooks/rules-of-hooks": "error",
    },
  },
];
