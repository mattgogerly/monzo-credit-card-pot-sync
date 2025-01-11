/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./node_modules/flowbite/**/*.js"
  ],
  darkMode: 'media',
  theme: {
    extend: {},
  },
  plugins: [
    require("flowbite/plugin")
  ]
}