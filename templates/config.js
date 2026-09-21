// Public page settings (not secret). This file is loaded by index.html and must be deployed with it.
window.APP_CONFIG = {
  // false: never call the API, always generate the PDF in the browser (no email option).
  // true: use the API and fall back to the browser only if the API is unreachable.
  USE_API: false,

  API_URL: "https://data-automation-reports-production.up.railway.app"
};
