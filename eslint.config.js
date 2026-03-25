import js from "@eslint/js";

export default [
  js.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    rules: {
      "no-unused-vars": "warn",
      "no-console": "off",
      "no-undef": "off"
    },
    ignores: [
      "node_modules/**",
      "dist/**",
      "dist-electron/**",
      "out/**"
    ]
  }
];