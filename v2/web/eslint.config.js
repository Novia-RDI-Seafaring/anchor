// Flat-config ESLint 9 setup for the Anchor web app.
//
// We intentionally keep this small: the v2 contract relies on TypeScript
// for most correctness, the import-linter contracts for layering on the
// Python side, and pytest/vitest for behaviour. ESLint catches the
// remaining JS-only footguns (unused imports, hooks rules, react-refresh
// boundary violations).
//
// Run from the repo root:
//   pnpm --dir web exec eslint src
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default tseslint.config(
  // Files ignored entirely. ``dist`` is the Vite build output; the test
  // snapshots and the generated vite-env types don't benefit from lint.
  {
    ignores: ["dist", "node_modules", "vite.config.ts.timestamp-*"],
  },

  // Recommended baselines.
  js.configs.recommended,
  ...tseslint.configs.recommended,

  // App-specific rules.
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
      // Allow underscore-prefixed unused vars (idiomatic for ignored
      // hook returns and React event handlers).
      "@typescript-eslint/no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
    },
  },
);
