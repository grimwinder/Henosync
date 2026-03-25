/** @type {import('eslint').Linter.Config[]} */
const config = [
    {
      files: ["**/*.{ts,tsx,js,jsx}"],
      rules: {
        "no-unused-vars": "warn",
        "no-console": "off"
      }
    }
  ];
  
  module.exports = config;